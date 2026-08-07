"""Family / sibling / near-miss / candidate-memory generator for the
CausalMemBench mini-pilot (SPEC.md sections 3-4, tech report 6.2/6.5/6.7).

Produces two strictly separated views of the benchmark:

  public_view/            (agent-visible; NO family/cell/program/near-miss
    tasks/*.json            labels -- only opaque ids, instruction text and
    memories/*.json         initial DB rows)
    tool_schema.json

  sealed/                 (evaluator-only; program specs, oracle plans,
    families.jsonl          family/cell labels, similarity records)
    tasks_sealed.jsonl
    memories_sealed.jsonl
    cells.jsonl
    oracle_report.json
    sim_report.csv
    manifest.json

Design notes
------------
* 8 parameterized program schemas across 4 business domains (CRM, inventory,
  ticket, calendar) = 4 abstract archetypes x 2 domain renderings each:
    conditional_write     (crm_escalate      / inv_overstock)
    two_row_transfer      (inv_transfer      / cal_move_headcount)
    aggregate_gate        (ticket_gate_close / cal_finalize)
    delete_after_capture  (crm_purge_lead    / ticket_purge_spam)
  The two domain renderings of an archetype share the same abstract
  signature, so they are program-match (P=1) by construction -- this is what
  the A10 (P=1,S=0) cell injects.
* Equivalence class == abstract signature (step set + partial order + check
  polarity + abstract role tags). Concrete thresholds and entities are
  instance parameters, never part of the class.
* One near-miss family z' per family keeps the domain surface but mutates one
  critical aspect of the program:
    P1: branch polarity flipped; P2: transfer direction reversed;
    P3: gate counts the wrong child-set ('done', >=1);
    P4: archive step removed (delete without capture).
  Each z' is itself executable and reaches its own legal terminal state.
* Initial states are drawn with three independent RNG streams: family params
  (fixed per family), sibling entities (fixed per sibling across seeds) and
  state distractors (per seed). For a fixed (sibling, seed) the initial state
  is therefore IDENTICAL across the six cells -- only the injected memory
  differs (paired design, SPEC section 5).

Usage:
  python generate_families.py --config configs/pilot.yaml [--skip-embedding]
"""

import argparse
import csv
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from program_dsl import ARCHETYPES, run_oracle_plan
from env_relationalops import RelationalOpsEnv

import yaml

# ---------------------------------------------------------------------------
# small utils
# ---------------------------------------------------------------------------

def sha_int(*parts):
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:12], 16)


def opaque_id(prefix, *parts):
    return "%s_%s" % (prefix, hashlib.sha1(
        "|".join(str(p) for p in parts).encode()).hexdigest()[:12])


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


STOPWORDS = set("""a an and are as at be but by for from has have if in into is it its of on or so
than that the their then there these this to was were will with without you your we our they he she
his her them him not no yes do does did each other any all both more most such only same own when
while before after once should must can could would may might shall about over under again every
""".split())

# Procedural boilerplate shared by ALL cards and instructions regardless of
# domain (agent-protocol vocabulary). Token overlap is measured on the
# remaining content tokens (domain nouns / entity words / values), which is
# what surface similarity S is about. Documented in pilot/README.md.
PROC_STOP = set("""read reads reading check checks checked checking verify verifies verified
verifying update updates updated write writes writing written confirm confirms confirmed insert
inserts inserted delete deletes deleted remove removes removed table tables row rows column columns
request requested policy rule rules apply applies applied current currently actual actually store
stores stored value values new back first verify confirm database state states status set sets
setting otherwise matching match matches matched narrow filter filters filtering lookup look looks
looked find finds found fetch get gets got retrieve retrieves name names entry entries record
records copy copies copied number numbers count counts counted amount amounts exactly report
reports reported note notes noted safety safe order ordering step steps procedure process goal
objective require requires required preconditions precondition postconditions postcondition guard
guards guards keep keeps kept stays stay hold holds holds true false done finish finished
finishing end ends episode episodes experience retrieved success outcomes outcome failure failures
applicable stated given use used using used decide decides decided decision decisions stop stops
stopped guessing invent inventing assume assumes assumed default defaults narrower restrictive
where tool tools message messages error errors argument arguments identifier identifiers identify
identifies ids id scope unrelated similar filter decide decisive according against within inside
outside across sure make makes made mean means meant mind careful carefully cheaper precise broad
quick verbose obvious obviously proper correctly right wrong final finally once twice digit digits
little least exceed exceeds exceeded exceeds remain remains remained remaining exist exists
existed existence available needed needs need instead inconsistency inconsistent flag flags
""".split())
STOPWORDS = STOPWORDS | PROC_STOP

TOKEN_RE = re.compile(r"[a-z0-9]+")


def content_tokens(text):
    # pure-digit tokens (step numbers, ids, thresholds) are instance
    # formatting, not lexical content; drop them from the overlap measure.
    return [t for t in TOKEN_RE.findall(text.lower())
            if t not in STOPWORDS and not t.isdigit()]


def tf_cosine(a, b):
    ca, cb = Counter(content_tokens(a)), Counter(content_tokens(b))
    if not ca or not cb:
        return 0.0
    dot = sum(v * cb.get(k, 0) for k, v in ca.items())
    na = sum(v * v for v in ca.values()) ** 0.5
    nb = sum(v * v for v in cb.values()) ** 0.5
    return dot / (na * nb)


# ---------------------------------------------------------------------------
# entity pools (surface transformations only, never labels)
# ---------------------------------------------------------------------------

FIRST = ["Aaron", "Bela", "Carmen", "Dmitri", "Elif", "Farah", "Gustav", "Hana",
         "Idris", "Jolene", "Kofi", "Lena", "Mateo", "Nadia", "Oren", "Priya",
         "Quentin", "Rosa", "Stefan", "Talia", "Umar", "Vera", "Wendell", "Xara",
         "Yusuf", "Zelda", "Mikael", "Noor", "Pablo", "Ingrid", "Tobias", "Sana"]
LAST = ["Almeida", "Brandt", "Cvetic", "Duarte", "Eriksen", "Fournier", "Gomes",
        "Haddad", "Iversen", "Jankovic", "Kowalski", "Lindqvist", "Moreau",
        "Novak", "Osman", "Petrova", "Quigley", "Rossi", "Sato", "Tanaka",
        "Urbaniak", "Varga", "Weiss", "Xiong", "Yilmaz", "Zhang", "Abara",
        "Bjornsson", "Castellano", "Demirci", "Okafor", "Nieminen"]
EMAIL_DOMAINS = ["example.com", "mail.example.org", "corp.example.net",
                 "sample.org", "demo.example.io"]
SKU_ALPHA = ["AX", "KB", "QM", "ZR", "TP", "LV", "NC", "WD"]
PRODUCT_WORDS = ["widget", "sprocket", "gasket", "valve", "sensor", "cable",
                 "bracket", "motor", "filter", "bearing", "relay", "switch"]
CATEGORIES = ["hardware", "electrical", "plumbing", "fasteners", "controls"]
TICKET_PREFIX = ["OPS", "INC", "SUP", "BUG", "SEC", "NET", "DBA", "APP"]
TICKET_TOPICS = ["login timeout", "sync failure", "export crash", "quota alert",
                 "stale cache", "permission error", "webhook loop", "index lag",
                 "billing mismatch", "password reset flood"]
EVENT_WORDS = ["Workshop", "Summit", "Review", "Briefing", "Seminar", "Forum",
               "Clinic", "Offsite", "Retreat", "Showcase"]
EVENT_TOPICS = ["Budget", "Roadmap", "Hiring", "Migration", "Security",
                "Design", "Vendor", "Release", "Support", "Training"]
ROOMS = ["A201", "B104", "C310", "D12", "E55", "F108", "G21", "H3"]
DATES = ["2026-09-03", "2026-09-10", "2026-09-17", "2026-09-24", "2026-10-01",
         "2026-10-08", "2026-10-15", "2026-10-22"]
CHANNELS = ["email", "phone", "chat", "onsite"]
QUEUES = ["tier1", "tier2", "escalations", "retention"]
SOURCES = ["webinar", "referral", "ads", "conference", "coldcall"]
TEAMS = ["north", "south", "central", "field"]


def person(rng, used):
    while True:
        n = "%s %s" % (rng.choice(FIRST), rng.choice(LAST))
        if n not in used:
            used.add(n)
            return n


def email_of(rng, name, used):
    base = name.lower().replace(" ", ".")
    dom = rng.choice(EMAIL_DOMAINS)
    e = "%s@%s" % (base, dom)
    if e in used:
        e = "%s.%d@%s" % (base, rng.randint(2, 99), dom)
    used.add(e)
    return e


# ---------------------------------------------------------------------------
# generic finish helper: build program + concrete oracle plan + instance dict
# ---------------------------------------------------------------------------

def finish_instance(archetype, tables, program_params, binding, terminal,
                    roles, instruction, meta):
    prog = ARCHETYPES[archetype](program_params)
    plan = []
    for s in prog["steps"]:           # builders list a valid linear extension
        a = dict(s["bind"](binding))
        a["step_id"] = s["id"]
        plan.append(a)
    return {"tables": tables, "instruction": instruction,
            "program_params": program_params, "signature": prog["signature"],
            "binding": binding, "terminal": terminal, "plan": plan,
            "roles": roles, "meta": meta}


# ===========================================================================
# P1 conditional_write: crm_escalate / inv_overstock
# ===========================================================================

CRM_TABLES_DOC = "customers(interactions)"
INV_TABLES_DOC = "stock(products, restock_orders)"


def sample_crm_escalate(rng, j):
    return {"join_depth": j, "op": ">",
            "theta": rng.randint(3, 9),
            "tier": rng.choice(["gold", "silver", "platinum"])}


def p1_roles(vocab, theta_phrase, conseq, alt, nm):
    cmp_txt = "at or below" if nm else "above"
    steps = ["Read the %s row for %s." % (vocab["table"], vocab["id_phrase"])]
    if vocab.get("policy_table"):
        steps.append("Find the applicable %s in the %s table (%s)."
                     % (theta_phrase, vocab["policy_table"], vocab["policy_how"]))
    steps += [
        "Compare the row's %s with the %s." % (vocab["cond_field"], theta_phrase),
        "If the %s is %s the %s, %s." % (vocab["cond_field"], cmp_txt, theta_phrase, conseq),
        "Otherwise, %s." % alt,
        "Read the row back and confirm the new values before finishing.",
    ]
    return {
        "goal": "Apply the %s policy to %s from the request."
                % (vocab["policy_name"], vocab["entity"]),
        "preconds": [
            "The request identifies %s." % vocab["id_phrase"],
            "The %s table contains the matching row." % vocab["table"],
        ],
        "steps": steps,
        "postconds": [
            "The row's %s and %s reflect the policy decision."
            % (vocab["set_f1"], vocab["set_f2"]),
        ],
        "guards": [
            "Never write without a WHERE that selects exactly the requested row.",
            "If the lookup returns no row or more than one row, stop and report "
            "instead of guessing.",
            "Do not invent %s; use the one given in the request." % vocab["id_phrase"],
        ],
    }


def p1_instruction(style, nm, j2, table, entity_desc, cond_field_text, theta_text,
                   conseq_text, alt_text, verify_hint):
    cmp_txt = "at or below" if nm else "above"
    if j2:
        rule = ("If the row's %s is %s %s, %s; otherwise, %s."
                % (cond_field_text, cmp_txt, theta_text, conseq_text, alt_text))
    else:
        rule = ("If the row's %s is %s %s, %s; otherwise, %s."
                % (cond_field_text, cmp_txt, theta_text, conseq_text, alt_text))
    if style == 0:
        return ("Maintenance request. A row for %s exists in the %s table. Policy: %s "
                "Verify the current value in the database first, apply the update, "
                "then read the row back to confirm it."
                % (entity_desc, table, rule))
    if style == 1:
        return ("Hi, could you take care of this? We have %s in the %s table. "
                "The rule is: %s Please check the actual value before you write "
                "anything, and confirm the row afterwards. Thanks!"
                % (entity_desc, table, rule))
    return ("Ops note: handle %s (see the %s table).\nRule: %s\n"
            "Check the stored value first, write the update, then verify the row."
            % (entity_desc, table, rule))


def build_crm_escalate(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    j2 = prm["join_depth"] == 2
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "crmesc"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "crmesc"))
    used_n, used_e = set(), set()
    name = person(rng_s, used_n)
    email = email_of(rng_s, name, used_e)
    tier, theta = prm["tier"], prm["theta"]
    delta = rng_s.randint(1, 3)
    branch = "A" if sib_idx % 2 == 0 else "B"
    complaints = theta + delta if branch == "A" else theta - delta
    eff_branch = branch
    if near_miss:
        eff_branch = "A" if complaints <= theta else "B"   # flipped program

    cust = {"id": rng_s.randint(100, 899), "name": name, "email": email,
            "tier": tier, "complaints": complaints, "status": "active",
            "priority_flag": 0, "lifetime_value": rng_s.randint(2, 40) * 500}
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    customers = [cust]
    for i in range(n_dis):
        nm_ = person(rng_d, used_n)
        em = email_of(rng_d, nm_, used_e)
        row = {"id": cust["id"] + 1 + i, "name": nm_, "email": em,
               "tier": rng_d.choice(["gold", "silver", "bronze", "trial"]),
               "complaints": rng_d.randint(0, theta + 4),
               "status": rng_d.choice(["active", "dormant", "closed"]),
               "priority_flag": rng_d.randint(0, 1),
               "lifetime_value": rng_d.randint(2, 40) * 500}
        if rng_d.random() < 0.15:        # missing-field injection (non-critical)
            row["tier"] = None
        customers.append(row)
    rng_d.shuffle(customers)
    interactions = [{"id": 500 + i,
                     "customer_email": rng_d.choice([r["email"] for r in customers]),
                     "date": rng_d.choice(DATES), "channel": rng_d.choice(CHANNELS),
                     "outcome": rng_d.choice(["resolved", "followup", "escalated"])}
                    for i in range(rng_d.randint(3, 8))]
    tables = {"customers": customers, "interactions": interactions}
    program_params = {
        "table": "customers", "key_field": "email", "key_value": email,
        "cond_field": "complaints",
        "cond_op": "<=" if near_miss else prm["op"],
        "theta": theta, "join_depth": prm["join_depth"],
        "write_a": {"tool": "update", "args": {"table": "customers",
                    "set": {"status": "escalated", "priority_flag": 1},
                    "where": {"email": email}}},
        "write_b": {"tool": "update", "args": {"table": "customers",
                    "set": {"status": "routine", "priority_flag": 0},
                    "where": {"email": email}}},
        "verify": {"table": "customers", "where": {"email": email}},
    }
    if j2:
        pol = [{"tier": tier, "escalate_threshold": theta, "queue": QUEUES[2]}]
        for t, s in (("gold", 1), ("silver", -1), ("bronze", 1), ("trial", -1),
                     ("platinum", 1)):
            if t != tier:
                pol.append({"tier": t,
                            "escalate_threshold": max(1, theta + rng_d.randint(1, 4) * s),
                            "queue": rng_d.choice(QUEUES)})
        rng_d.shuffle(pol)
        tables["sla_policies"] = pol
        program_params.update({
            "policy_table": "sla_policies", "policy_key_field": "tier",
            "policy_key_value": tier, "policy_value_field": "escalate_threshold"})
    exp = ({"status": "escalated", "priority_flag": 1} if eff_branch == "A"
           else {"status": "routine", "priority_flag": 0})
    terminal = [
        {"type": "field_cmp", "table": "customers", "where": {"email": email},
         "field": "status", "op": "==", "value": exp["status"]},
        {"type": "field_cmp", "table": "customers", "where": {"email": email},
         "field": "priority_flag", "op": "==", "value": exp["priority_flag"]},
    ]
    theta_phrase = ("escalation threshold from the sla_policies table" if j2
                    else "complaint threshold stated in the request")
    roles = p1_roles(
        {"policy_name": "escalation", "entity": "the customer", "table": "customers",
         "id_phrase": "the customer's email address", "cond_field": "complaint count",
         "set_f1": "status", "set_f2": "priority_flag",
         "policy_table": "sla_policies" if j2 else None,
         "policy_how": "match the customer's tier and read escalate_threshold"},
        theta_phrase,
        "set status to 'escalated' and priority_flag to 1",
        "set status to 'routine' and priority_flag to 0", near_miss)
    if j2:
        theta_text = ("the escalation threshold for tier '%s' in the sla_policies "
                      "table (column escalate_threshold)" % tier)
    else:
        theta_text = str(theta)
    cmp_txt = "at or below" if near_miss else "above"
    rule = ("If the customer's complaint count is %s %s, set status to 'escalated' "
            "and priority_flag to 1; otherwise, set status to 'routine' and "
            "priority_flag to 0." % (cmp_txt, theta_text))
    if style == 0:
        instr = ("CRM maintenance request. A record for %s (%s) exists in the customers "
                 "table. Policy: %s Verify the current complaint count in the database "
                 "first, apply the update, then read the row back to confirm it."
                 % (name, email, rule))
    elif style == 1:
        instr = ("Hi, could you take care of this customer account? %s (%s), tier '%s', "
                 "is in the customers table. The rule is: %s Please check the actual "
                 "count before you write anything, and confirm the row afterwards. Thanks!"
                 % (name, email, tier, rule))
    else:
        instr = ("Ops note: handle account %s (%s) in the customers table.\nRule: %s\n"
                 "Check the stored complaint count first, write the update, then verify "
                 "the row." % (name, email, rule))
    return finish_instance(
        "conditional_write", tables, program_params, {"branch": eff_branch},
        terminal, roles, instr,
        {"entity_name": name, "entity_email": email, "theta": theta, "tier": tier,
         "complaints": complaints, "n_distractors": n_dis})


def sample_inv_overstock(rng, j):
    return {"join_depth": j, "op": ">",
            "limit": rng.randint(30, 80),
            "category": rng.choice(CATEGORIES)}


def build_inv_overstock(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    j2 = prm["join_depth"] == 2
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "invover"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "invover"))
    sku = "%s-%04d" % (rng_s.choice(SKU_ALPHA), rng_s.randint(1000, 9999))
    pname = "%s %s" % (rng_s.choice(PRODUCT_WORDS), rng_s.choice(PRODUCT_WORDS))
    cat, limit = prm["category"], prm["limit"]
    delta = rng_s.randint(2, 12)
    branch = "A" if sib_idx % 2 == 0 else "B"
    qty = limit + delta if branch == "A" else limit - delta
    eff_branch = branch
    if near_miss:
        eff_branch = "A" if qty <= limit else "B"

    srow = {"id": rng_s.randint(100, 899), "sku": sku, "warehouse": "main",
            "qty": qty, "flag": "normal", "review": 0}
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    stock = [srow]
    used_sku = {sku}
    for i in range(n_dis):
        s2 = "%s-%04d" % (rng_d.choice(SKU_ALPHA), rng_d.randint(1000, 9999))
        if s2 in used_sku:
            s2 = s2 + "X"
        used_sku.add(s2)
        stock.append({"id": srow["id"] + 1 + i, "sku": s2,
                      "warehouse": rng_d.choice(["main", "east", "west"]),
                      "qty": rng_d.randint(0, limit + 20),
                      "flag": rng_d.choice(["normal", "ok", "watch"]),
                      "review": rng_d.randint(0, 1)})
    rng_d.shuffle(stock)
    products = [{"id": 10 + i, "sku": s2, "name": "%s unit" % rng_d.choice(PRODUCT_WORDS),
                 "category": rng_d.choice(CATEGORIES),
                 "price": rng_d.randint(5, 400)}
                for i, s2 in enumerate([r["sku"] for r in stock][:10])]
    products.insert(0, {"id": 9, "sku": sku, "name": pname, "category": cat,
                        "price": rng_s.randint(20, 400)})
    restock = [{"id": 700 + i, "sku": rng_d.choice(list(used_sku - {sku})),
                "qty": rng_d.randint(1, 30),
                "status": rng_d.choice(["pending", "done"]),
                "note": "auto reorder"} for i in range(rng_d.randint(2, 6))]
    tables = {"stock": stock, "products": products, "restock_orders": restock}
    program_params = {
        "table": "stock", "key_field": "sku", "key_value": sku,
        "cond_field": "qty",
        "cond_op": "<=" if near_miss else prm["op"],
        "theta": limit, "join_depth": prm["join_depth"],
        "write_a": {"tool": "update", "args": {"table": "stock",
                    "set": {"flag": "markdown", "review": 1},
                    "where": {"sku": sku, "warehouse": "main"}}},
        "write_b": {"tool": "update", "args": {"table": "stock",
                    "set": {"flag": "ok", "review": 0},
                    "where": {"sku": sku, "warehouse": "main"}}},
        "verify": {"table": "stock", "where": {"sku": sku, "warehouse": "main"}},
    }
    # NOTE: read filter for the target row is sku only (single 'main' row for
    # that sku is guaranteed by construction: only one row per sku).
    if j2:
        pol = [{"category": cat, "overstock_limit": limit, "action": "markdown"}]
        for c, s in ((c_, 1) for c_ in CATEGORIES):
            if c != cat:
                pol.append({"category": c,
                            "overstock_limit": max(5, limit + rng_d.randint(3, 15) * s),
                            "action": rng_d.choice(["markdown", "hold"])})
        rng_d.shuffle(pol)
        tables["inv_policies"] = pol
        program_params.update({
            "policy_table": "inv_policies", "policy_key_field": "category",
            "policy_key_value": cat, "policy_value_field": "overstock_limit"})
    exp = ({"flag": "markdown", "review": 1} if eff_branch == "A"
           else {"flag": "ok", "review": 0})
    terminal = [
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": "main"},
         "field": "flag", "op": "==", "value": exp["flag"]},
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": "main"},
         "field": "review", "op": "==", "value": exp["review"]},
    ]
    roles = p1_roles(
        {"policy_name": "overstock", "entity": "the stocked item", "table": "stock",
         "id_phrase": "the item's SKU", "cond_field": "on-hand quantity",
         "set_f1": "flag", "set_f2": "review",
         "policy_table": "inv_policies" if j2 else None,
         "policy_how": "match the product category and read overstock_limit"},
        ("overstock limit from the inv_policies table" if j2
         else "overstock limit stated in the request"),
        "set flag to 'markdown' and review to 1",
        "set flag to 'ok' and review to 0", near_miss)
    if j2:
        theta_text = ("the overstock limit for category '%s' in the inv_policies "
                      "table (column overstock_limit)" % cat)
    else:
        theta_text = str(limit)
    cmp_txt = "at or below" if near_miss else "above"
    rule = ("If the on-hand quantity of SKU %s at warehouse 'main' is %s %s, set its "
            "flag to 'markdown' and review to 1; otherwise, set flag to 'ok' and "
            "review to 0." % (sku, cmp_txt, theta_text))
    if style == 0:
        instr = ("Inventory maintenance request. SKU %s (%s, category '%s') is tracked "
                 "in the stock table. Policy: %s Verify the current quantity first, "
                 "apply the update, then read the row back to confirm it."
                 % (sku, pname, cat, rule))
    elif style == 1:
        instr = ("Hi, could you check item %s (%s)? It's in the stock table, warehouse "
                 "'main'. The rule is: %s Please look at the real quantity before "
                 "writing, and confirm the row afterwards. Thanks!" % (sku, pname, rule))
    else:
        instr = ("Ops note: handle SKU %s (warehouse 'main') in the stock table.\n"
                 "Rule: %s\nCheck the stored quantity first, write the update, then "
                 "verify the row." % (sku, rule))
    return finish_instance(
        "conditional_write", tables, program_params, {"branch": eff_branch},
        terminal, roles, instr,
        {"sku": sku, "limit": limit, "category": cat, "qty": qty,
         "n_distractors": n_dis})


# ===========================================================================
# P2 two_row_transfer: inv_transfer / cal_move_headcount
#   READ origin row ; READ target row (unordered) ; CHECK balance guard
#   ; WRITE origin ; WRITE target (unordered) ; VERIFY
# near-miss: transfer direction reversed (origin/target roles swapped)
# ===========================================================================

def p2_roles(vocab, nm):
    move = ("Move the requested amount from the %s back into the %s"
            % (vocab["dst"], vocab["src"])) if nm else \
           ("Move the requested amount from the %s into the %s"
            % (vocab["src"], vocab["dst"]))
    return {
        "goal": "Rebalance %s between the %s and the %s."
                % (vocab["what"], vocab["src"], vocab["dst"]),
        "preconds": [
            "The request states the amount to move and identifies both rows.",
            "Both rows exist in the %s table." % vocab["table"],
        ],
        "steps": [
            "Read the %s row and the %s row (either order)." % (vocab["src"], vocab["dst"]),
            "Check the guard: the %s must keep at least %s after the move, and the "
            "%s must not exceed %s." % (vocab["src"], vocab["min_text"],
                                        vocab["dst"], vocab["cap_text"]),
            move + ": subtract the amount from the %s and add it to the %s."
                    % (vocab["src"], vocab["dst"]),
            "If the guard fails, do not move anything and report the violation instead.",
            "Read both rows again and confirm the new values before finishing.",
        ],
        "postconds": [
            "The %s is reduced and the %s is increased by exactly the requested amount."
            % (vocab["src"], vocab["dst"]),
        ],
        "guards": [
            "Never write before the guard check has passed.",
            "Compute the new values from the numbers you actually read; do not copy "
            "numbers from the request into the rows.",
            "Always update both sides with a restrictive WHERE each.",
        ],
    }


def sample_inv_transfer(rng, j):
    return {"amount": rng.randint(3, 15), "min_keep": rng.choice([0, 2, 5]),
            "cap": 400}


def build_inv_transfer(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "invtr"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "invtr"))
    sku = "%s-%04d" % (rng_s.choice(SKU_ALPHA), rng_s.randint(1000, 9999))
    pname = "%s assembly" % rng_s.choice(PRODUCT_WORDS)
    amount, min_keep, cap = prm["amount"], prm["min_keep"], prm["cap"]
    e0 = rng_s.randint(amount + min_keep + 5, amount + min_keep + 45)
    w0 = rng_s.randint(5, 60)
    # correct program: move 'amount' east -> west; near-miss: west -> east
    src_wh, dst_wh = ("west", "east") if near_miss else ("east", "west")
    eid, wid = rng_s.randint(100, 499), rng_s.randint(500, 899)
    stock = [
        {"id": eid, "sku": sku, "warehouse": "east", "qty": e0, "flag": "normal", "review": 0},
        {"id": wid, "sku": sku, "warehouse": "west", "qty": w0, "flag": "normal", "review": 0},
    ]
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    used = {sku}
    for i in range(n_dis):
        s2 = "%s-%04d" % (rng_d.choice(SKU_ALPHA), rng_d.randint(1000, 9999))
        if s2 in used:
            s2 += "X"
        used.add(s2)
        stock.append({"id": 900 + i, "sku": s2,
                      "warehouse": rng_d.choice(["east", "west", "main"]),
                      "qty": rng_d.randint(0, 90), "flag": rng_d.choice(["normal", "ok"]),
                      "review": rng_d.randint(0, 1)})
    rng_d.shuffle(stock)
    products = [{"id": 10 + i, "sku": s2, "name": "%s unit" % rng_d.choice(PRODUCT_WORDS),
                 "category": rng_d.choice(CATEGORIES), "price": rng_d.randint(5, 400)}
                for i, s2 in enumerate(list(used)[:10])]
    restock = [{"id": 700 + i, "sku": rng_d.choice(list(used - {sku})),
                "qty": rng_d.randint(1, 30), "status": rng_d.choice(["pending", "done"]),
                "note": "auto reorder"} for i in range(rng_d.randint(2, 6))]
    tables = {"stock": stock, "products": products, "restock_orders": restock}
    qty_src = w0 if near_miss else e0
    qty_dst = e0 if near_miss else w0
    guard = {"kind": "transfer_guard",
             "a": {"table": "stock", "where": {"sku": sku, "warehouse": src_wh}, "field": "qty"},
             "b": {"table": "stock", "where": {"sku": sku, "warehouse": dst_wh}, "field": "qty"},
             "amount": amount, "min_a": min_keep, "cap_b": cap}
    program_params = {
        "class_tag": "transfer:target>origin" if near_miss else "transfer:origin>target",
        "read_a": {"table": "stock", "filter": {"sku": sku, "warehouse": src_wh}},
        "read_b": {"table": "stock", "filter": {"sku": sku, "warehouse": dst_wh}},
        "guard": guard,
        "write_a": {"tool": "update", "args": {"table": "stock",
                    "set": {"qty": qty_src - amount},
                    "where": {"sku": sku, "warehouse": src_wh}}},
        "write_b": {"tool": "update", "args": {"table": "stock",
                    "set": {"qty": qty_dst + amount},
                    "where": {"sku": sku, "warehouse": dst_wh}}},
        "verify": {"table": "stock", "where": {"sku": sku}},
    }
    terminal = [
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": src_wh},
         "field": "qty", "op": "==", "value": qty_src - amount},
        {"type": "field_cmp", "table": "stock", "where": {"sku": sku, "warehouse": dst_wh},
         "field": "qty", "op": "==", "value": qty_dst + amount},
    ]
    vocab = {"what": "stock", "src": "'%s' warehouse row" % src_wh,
             "dst": "'%s' warehouse row" % dst_wh, "table": "stock",
             "min_text": "the minimum keep level", "cap_text": "its capacity"}
    roles = p2_roles(vocab, False)   # text already encodes the (possibly swapped) direction
    move_line = ("move %d units of SKU %s from warehouse '%s' to warehouse '%s'"
                 % (amount, sku, src_wh, dst_wh))
    if style == 0:
        instr = ("Inventory rebalancing request. In the stock table, %s. The '%s' row "
                 "must keep at least %d units afterwards; the '%s' side must not exceed "
                 "%d. Read both rows, check the guard, then apply both updates and "
                 "verify." % (move_line, src_wh, min_keep, dst_wh, cap))
    elif style == 1:
        instr = ("Hi, warehouse ops here — could you %s for us (%s, in the stock table)? "
                 "Guard: '%s' must stay at %d or more after the move; '%s' may not go over "
                 "%d. Check the numbers first, do both updates, then make sure the rows "
                 "look right." % (move_line, pname, src_wh, min_keep, dst_wh, cap))
    else:
        instr = ("Ops note: %s (stock table).\nGuard: '%s' >= %d after the move; '%s' <= "
                 "%d.\nRead both rows, check, update both, verify." % (move_line, src_wh,
                 min_keep, dst_wh, cap))
    return finish_instance(
        "two_row_transfer", tables, program_params, {"branch": "A"},
        terminal, roles, instr,
        {"sku": sku, "amount": amount, "min_keep": min_keep, "cap": cap,
         "src_wh": src_wh, "dst_wh": dst_wh, "qty_src0": qty_src, "qty_dst0": qty_dst,
         "n_distractors": n_dis})


def sample_cal_move(rng, j):
    return {"amount": rng.randint(2, 10), "min_keep": 5}


def build_cal_move_headcount(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "calmv"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "calmv"))
    title = "%s %s" % (rng_s.choice(EVENT_TOPICS), rng_s.choice(EVENT_WORDS))
    date = rng_s.choice(DATES)
    amount, min_keep = prm["amount"], prm["min_keep"]
    # Role-level values first (source must ALWAYS satisfy the guard, whether
    # the source is the morning or the afternoon session), then map to rows.
    h_src = rng_s.randint(amount + min_keep + 3, amount + min_keep + 25)
    h_dst = rng_s.randint(3, 30)
    cap_dst = h_dst + amount + rng_s.randint(3, 20)
    cap_src = h_src + rng_s.randint(10, 40)
    src_slot, dst_slot = (("afternoon", "morning") if near_miss
                          else ("morning", "afternoon"))
    slot_rows = {src_slot: {"headcount": h_src, "capacity": cap_src},
                 dst_slot: {"headcount": h_dst, "capacity": cap_dst}}
    idA, idB = rng_s.randint(100, 499), rng_s.randint(500, 899)
    events = [
        {"id": idA, "title": title, "slot": "morning", "date": date,
         "start": "09:00", "room": rng_s.choice(ROOMS), "status": "scheduled",
         "owner": person(rng_s, set()), **slot_rows["morning"]},
        {"id": idB, "title": title, "slot": "afternoon", "date": date,
         "start": "14:00", "room": rng_s.choice(ROOMS), "status": "scheduled",
         "owner": person(rng_s, set()), **slot_rows["afternoon"]},
    ]
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    for i in range(n_dis):
        t2 = "%s %s" % (rng_d.choice(EVENT_TOPICS), rng_d.choice(EVENT_WORDS))
        if t2 == title:          # never let a distractor match the target key
            t2 += " Plus"
        events.append({"id": 900 + i, "title": t2,
                       "slot": rng_d.choice(["morning", "afternoon", "evening"]),
                       "date": rng_d.choice(DATES), "start": rng_d.choice(["09:00", "11:00", "14:00"]),
                       "room": rng_d.choice(ROOMS), "headcount": rng_d.randint(2, 60),
                       "capacity": rng_d.randint(40, 90), "status": rng_d.choice(["scheduled", "tentative"]),
                       "owner": person(rng_d, set())})
    rng_d.shuffle(events)
    attendees = [{"id": 300 + i, "event_id": rng_d.choice([e["id"] for e in events]),
                  "person": person(rng_d, set()), "rsvp": rng_d.choice(["accepted", "declined", "pending"]),
                  "email": "att%d@example.com" % i} for i in range(rng_d.randint(5, 12))]
    notes = [{"id": 600 + i, "person": person(rng_d, set()), "message": "reminder",
              "kind": rng_d.choice(["reminder", "info"])} for i in range(rng_d.randint(2, 5))]
    tables = {"events": events, "attendees": attendees, "notifications": notes}
    guard = {"kind": "transfer_guard",
             "a": {"table": "events", "where": {"title": title, "slot": src_slot}, "field": "headcount"},
             "b": {"table": "events", "where": {"title": title, "slot": dst_slot}, "field": "headcount"},
             "amount": amount, "min_a": min_keep, "cap_b": cap_dst}
    program_params = {
        "class_tag": "transfer:target>origin" if near_miss else "transfer:origin>target",
        "read_a": {"table": "events", "filter": {"title": title, "slot": src_slot}},
        "read_b": {"table": "events", "filter": {"title": title, "slot": dst_slot}},
        "guard": guard,
        "write_a": {"tool": "update", "args": {"table": "events",
                    "set": {"headcount": h_src - amount},
                    "where": {"title": title, "slot": src_slot}}},
        "write_b": {"tool": "update", "args": {"table": "events",
                    "set": {"headcount": h_dst + amount},
                    "where": {"title": title, "slot": dst_slot}}},
        "verify": {"table": "events", "where": {"title": title}},
    }
    terminal = [
        {"type": "field_cmp", "table": "events", "where": {"title": title, "slot": src_slot},
         "field": "headcount", "op": "==", "value": h_src - amount},
        {"type": "field_cmp", "table": "events", "where": {"title": title, "slot": dst_slot},
         "field": "headcount", "op": "==", "value": h_dst + amount},
    ]
    vocab = {"what": "headcount", "src": "'%s' session" % src_slot,
             "dst": "'%s' session" % dst_slot, "table": "events",
             "min_text": "the minimum floor", "cap_text": "its room capacity"}
    roles = p2_roles(vocab, False)
    move_line = ("move %d attendees of '%s' from the %s session to the %s session"
                 % (amount, title, src_slot, dst_slot))
    if style == 0:
        instr = ("Scheduling request (%s). In the events table, %s. The %s session must "
                 "keep at least %d attendees afterwards; the %s session's headcount must "
                 "not exceed its capacity (%d). Read both sessions, check the guard, then "
                 "apply both updates and verify." % (date, move_line, src_slot, min_keep,
                 dst_slot, cap_dst))
    elif style == 1:
        instr = ("Hi, could you %s? Both sessions are in the events table (same title "
                 "'%s', date %s). Guard: %s stays at %d+; %s must not exceed capacity "
                 "(%d). Check the numbers first, do both updates, then confirm."
                 % (move_line, title, date, src_slot, min_keep, dst_slot, cap_dst))
    else:
        instr = ("Ops note: %s (events table, date %s).\nGuard: %s >= %d after the move; "
                 "%s <= capacity %d.\nRead both rows, check, update both, verify."
                 % (move_line, date, src_slot, min_keep, dst_slot, cap_dst))
    return finish_instance(
        "two_row_transfer", tables, program_params, {"branch": "A"},
        terminal, roles, instr,
        {"title": title, "date": date, "amount": amount, "min_keep": min_keep,
         "src_slot": src_slot, "dst_slot": dst_slot, "h_src0": h_src, "h_dst0": h_dst,
         "cap_dst": cap_dst, "n_distractors": n_dis})


# ===========================================================================
# P3 aggregate_gate: ticket_gate_close / cal_finalize
#   READ parent ; AGGREGATE children ; CHECK agg (== 0 or, NM: >= 1)
#   ; WRITE parent update ; WRITE log insert (unordered) ; VERIFY
# near-miss: gate counts the WRONG child-set (completed items, >= 1)
# ===========================================================================

def p3_roles(vocab, nm):
    if nm:
        gate = ("Count how many %s are already %s. If at least one is %s, %s; "
                "otherwise, %s." % (vocab["children"], vocab["done_word"],
                                    vocab["done_word"], vocab["conseq_nm"],
                                    vocab["alt_nm"]))
    else:
        gate = ("Count how many %s are still %s. If none remain, %s; otherwise, %s."
                % (vocab["children"], vocab["open_word"], vocab["conseq"],
                   vocab["alt"]))
    return {
        "goal": vocab["goal"],
        "preconds": [
            "The request names %s." % vocab["parent_phrase"],
            "The %s rows are linked to it in the %s table." % (vocab["children"], vocab["child_table"]),
        ],
        "steps": [
            "Read the %s row for %s." % (vocab["parent_table"], vocab["parent_phrase"]),
            "Aggregate over the linked %s in the %s table." % (vocab["children"], vocab["child_table"]),
            gate,
            "Write the status update on the %s row." % vocab["parent_table"],
            "Insert a matching entry into the %s table (either order of the two writes is fine)." % vocab["log_table"],
            "Read the %s row back and confirm before finishing." % vocab["parent_table"],
        ],
        "postconds": [vocab["postcond"]],
        "guards": [
            "Never decide from the request text alone; run the aggregate yourself.",
            "Report the count you used if it is zero versus positive.",
            "Use a restrictive WHERE for every write.",
        ],
    }


def sample_ticket_gate(rng, j):
    return {"prefix": rng.choice(TICKET_PREFIX),
            "topic": rng.choice(TICKET_TOPICS)}


def build_ticket_gate_close(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "tickg"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "tickg"))
    prm = fp["params"]
    tkey = "%s-%d" % (prm["prefix"], rng_s.randint(1000, 9999))
    title = prm["topic"]
    reporter = person(rng_s, set())
    assignee = person(rng_s, set())
    branch = "A" if sib_idx % 2 == 0 else "B"
    n_sub = rng_s.randint(3, 5)
    if branch == "A":
        statuses = ["done"] * n_sub
    else:
        n_open = rng_s.randint(1, n_sub - 1)
        statuses = ["done"] * (n_sub - n_open) + ["open"] * n_open
        rng_s.shuffle(statuses)
    open_n = sum(1 for st in statuses if st != "done")
    done_n = n_sub - open_n
    if near_miss:
        # z': >=1 completed child -> close (conseq), else keep working (alt)
        eff_branch = "A" if done_n >= 1 else "B"
    else:
        eff_branch = "A" if open_n == 0 else "B"

    tid = rng_s.randint(100, 899)
    tickets = [{"id": tid, "tkey": tkey, "title": title,
                "priority": rng_s.choice(["p1", "p2", "p3"]), "status": "open",
                "assignee": assignee, "reporter": reporter, "tag": "normal"}]
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    used_keys = {tkey}
    for i in range(n_dis):
        k2 = "%s-%d" % (rng_d.choice(TICKET_PREFIX), rng_d.randint(1000, 9999))
        if k2 in used_keys:
            k2 += "Z"
        used_keys.add(k2)
        tickets.append({"id": 900 + i, "tkey": k2, "title": rng_d.choice(TICKET_TOPICS),
                        "priority": rng_d.choice(["p1", "p2", "p3"]),
                        "status": rng_d.choice(["open", "in_progress", "resolved", "closed"]),
                        "assignee": person(rng_d, set()), "reporter": person(rng_d, set()),
                        "tag": rng_d.choice(["normal", "vip", "watch"])})
    rng_d.shuffle(tickets)
    subtasks = [{"id": 200 + j, "tkey": tkey, "title": "step %d" % (j + 1),
                 "status": st} for j, st in enumerate(statuses)]
    for i in range(rng_d.randint(4, 10)):
        subtasks.append({"id": 400 + i, "tkey": rng_d.choice(list(used_keys - {tkey})),
                         "title": "sub %d" % i,
                         "status": rng_d.choice(["done", "open", "blocked"])})
    rng_d.shuffle(subtasks)
    events = [{"id": 800 + i, "tkey": rng_d.choice(list(used_keys - {tkey})),
               "etype": rng_d.choice(["comment", "status_change"]),
               "note": "routine log"} for i in range(rng_d.randint(2, 5))]
    tables = {"tickets": tickets, "subtasks": subtasks, "ticket_events": events}
    if near_miss:
        agg_args = {"table": "subtasks", "agg": "count",
                    "filter": {"tkey": tkey, "status": "done"}}
        check = {"kind": "agg_cmp", "op": ">=", "value": 1}
        agg_sem = "done"
    else:
        agg_args = {"table": "subtasks", "agg": "count",
                    "filter": {"tkey": tkey, "status": {"$ne": "done"}}}
        check = {"kind": "agg_cmp", "op": "==", "value": 0}
        agg_sem = "open"
    note_b = ("Blocked: %d subtask(s) still open." % open_n) if not near_miss else \
             "Resolution criteria not met."
    program_params = {
        "agg_sem": agg_sem,
        "read_parent": {"table": "tickets", "filter": {"tkey": tkey}},
        "agg_args": agg_args, "check": check,
        "write_parent_a": {"tool": "update", "args": {"table": "tickets",
                           "set": {"status": "resolved"}, "where": {"tkey": tkey}}},
        "write_parent_b": {"tool": "update", "args": {"table": "tickets",
                           "set": {"status": "in_progress"}, "where": {"tkey": tkey}}},
        "write_log_a": {"tool": "insert", "args": {"table": "ticket_events",
                        "record": {"id": 7001, "tkey": tkey, "etype": "resolution",
                                   "note": "All subtasks completed; ticket resolved."}}},
        "write_log_b": {"tool": "insert", "args": {"table": "ticket_events",
                        "record": {"id": 7002, "tkey": tkey, "etype": "comment",
                                   "note": note_b}}},
        "verify": {"table": "tickets", "where": {"tkey": tkey}},
    }
    exp_status = "resolved" if eff_branch == "A" else "in_progress"
    exp_etype = "resolution" if eff_branch == "A" else "comment"
    terminal = [
        {"type": "field_cmp", "table": "tickets", "where": {"tkey": tkey},
         "field": "status", "op": "==", "value": exp_status},
        {"type": "exists", "table": "ticket_events",
         "where": {"tkey": tkey, "etype": exp_etype}},
    ]
    if near_miss:
        roles = p3_roles(
            {"children": "subtasks", "done_word": "complete", "open_word": "open",
             "conseq_nm": "mark the ticket 'resolved' and log a 'resolution' entry",
             "alt_nm": "set the ticket to 'in_progress' and add a plain comment",
             "goal": "Triage the ticket from the request according to its subtask progress.",
             "parent_phrase": "the ticket key", "child_table": "subtasks",
             "parent_table": "tickets", "log_table": "ticket_events",
             "postcond": "The ticket status and its log entry match the subtask situation."},
            True)
        rule = ("If at least one subtask of ticket %s is complete, mark the ticket "
                "'resolved' and log a 'resolution' entry in ticket_events (use id 7001); "
                "otherwise set it to 'in_progress' and add a 'comment' entry (id 7002)."
                % tkey)
    else:
        roles = p3_roles(
            {"children": "subtasks", "done_word": "complete", "open_word": "open",
             "conseq": "mark the ticket 'resolved' and log a 'resolution' entry",
             "alt": "set the ticket to 'in_progress' and add a comment with the open count",
             "goal": "Close out the ticket from the request once its subtasks are all complete.",
             "parent_phrase": "the ticket key", "child_table": "subtasks",
             "parent_table": "tickets", "log_table": "ticket_events",
             "postcond": "The ticket is resolved exactly when no open subtasks remain, with a matching log entry."},
            False)
        rule = ("If no subtask of ticket %s is still open (count of subtasks whose status "
                "is not 'done' equals 0), mark the ticket 'resolved' and log a 'resolution' "
                "entry in ticket_events (use id 7001); otherwise set it to 'in_progress' "
                "and add a 'comment' entry noting how many remain open (id 7002)." % tkey)
    if style == 0:
        instr = ("Service desk request. Ticket %s ('%s', filed by %s) is in the tickets "
                 "table; its subtasks are in the subtasks table. Policy: %s Verify the "
                 "counts yourself before writing."
                 % (tkey, title, reporter, rule))
    elif style == 1:
        instr = ("Hi! Could you process ticket %s ('%s')? %s The subtasks table holds "
                 "its steps. Please aggregate the subtasks first, then write the update "
                 "and the log entry. Thanks!" % (tkey, title, rule))
    else:
        instr = ("Ops note: process ticket %s ('%s').\nPolicy: %s\nAggregate first, then "
                 "write both the status and the log entry." % (tkey, title, rule))
    return finish_instance(
        "aggregate_gate", tables, program_params, {"branch": eff_branch},
        terminal, roles, instr,
        {"tkey": tkey, "n_sub": n_sub, "open_n": open_n, "done_n": done_n,
         "n_distractors": n_dis})


def sample_cal_finalize(rng, j):
    return {"topic": rng.choice(EVENT_TOPICS), "word": rng.choice(EVENT_WORDS)}


def build_cal_finalize(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "calfin"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "calfin"))
    prm = fp["params"]
    title = "%s %s" % (prm["topic"], prm["word"])
    date = rng_s.choice(DATES)
    owner = person(rng_s, set())
    branch = "A" if sib_idx % 2 == 0 else "B"
    n_att = rng_s.randint(4, 7)
    if branch == "A":
        rsvps = [rng_s.choice(["accepted", "pending"]) for _ in range(n_att)]
    else:
        n_dec = rng_s.randint(1, n_att - 1)
        rsvps = ["declined"] * n_dec + [rng_s.choice(["accepted", "pending"])
                                        for _ in range(n_att - n_dec)]
        rng_s.shuffle(rsvps)
    dec_n = sum(1 for r in rsvps if r == "declined")
    acc_n = sum(1 for r in rsvps if r == "accepted")
    if near_miss:
        eff_branch = "A" if acc_n >= 1 else "B"   # z': >=1 accepted -> confirm
    else:
        eff_branch = "A" if dec_n == 0 else "B"

    eid = rng_s.randint(100, 899)
    events = [{"id": eid, "title": title, "slot": rng_s.choice(["morning", "afternoon"]),
               "date": date, "start": rng_s.choice(["09:00", "11:00", "14:00"]),
               "room": rng_s.choice(ROOMS), "headcount": n_att,
               "capacity": rng_s.randint(30, 80), "status": "tentative", "owner": owner}]
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    for i in range(n_dis):
        t2 = "%s %s" % (rng_d.choice(EVENT_TOPICS), rng_d.choice(EVENT_WORDS))
        if t2 == title:          # never let a distractor match the target key
            t2 += " Plus"
        events.append({"id": 900 + i, "title": t2,
                       "slot": rng_d.choice(["morning", "afternoon", "evening"]),
                       "date": rng_d.choice(DATES), "start": rng_d.choice(["09:00", "11:00"]),
                       "room": rng_d.choice(ROOMS), "headcount": rng_d.randint(2, 60),
                       "capacity": rng_d.randint(40, 90),
                       "status": rng_d.choice(["scheduled", "tentative", "confirmed"]),
                       "owner": person(rng_d, set())})
    rng_d.shuffle(events)
    attendees = [{"id": 300 + j, "event_id": eid, "person": person(rng_s, set()),
                  "rsvp": rsvps[j], "email": "guest%d@example.com" % j}
                 for j in range(n_att)]
    for i in range(rng_d.randint(5, 12)):
        attendees.append({"id": 500 + i,
                          "event_id": rng_d.choice([e["id"] for e in events if e["id"] != eid]),
                          "person": person(rng_d, set()),
                          "rsvp": rng_d.choice(["accepted", "declined", "pending"]),
                          "email": "att%d@example.com" % i})
    tables = {"events": events, "attendees": attendees, "notifications": [
        {"id": 600 + i, "person": person(rng_d, set()), "message": "reminder",
         "kind": "reminder"} for i in range(rng_d.randint(2, 5))]}
    if near_miss:
        agg_args = {"table": "attendees", "agg": "count",
                    "filter": {"event_id": eid, "rsvp": "accepted"}}
        check = {"kind": "agg_cmp", "op": ">=", "value": 1}
        agg_sem = "done"
    else:
        agg_args = {"table": "attendees", "agg": "count",
                    "filter": {"event_id": eid, "rsvp": "declined"}}
        check = {"kind": "agg_cmp", "op": "==", "value": 0}
        agg_sem = "open"
    msg_a = "Event '%s' on %s confirmed; no declines registered." % (title, date)
    msg_b = ("Event '%s' on %s needs review: %d attendee(s) declined." % (title, date, dec_n)
             if not near_miss else "Confirmation criteria not met.")
    program_params = {
        "agg_sem": agg_sem,
        "read_parent": {"table": "events", "filter": {"title": title}},
        "agg_args": agg_args, "check": check,
        "write_parent_a": {"tool": "update", "args": {"table": "events",
                           "set": {"status": "confirmed"},
                           "where": {"title": title, "date": date}}},
        "write_parent_b": {"tool": "update", "args": {"table": "events",
                           "set": {"status": "needs_review"},
                           "where": {"title": title, "date": date}}},
        "write_log_a": {"tool": "insert", "args": {"table": "notifications",
                        "record": {"id": 8101, "person": owner, "message": msg_a,
                                   "kind": "confirmation"}}},
        "write_log_b": {"tool": "insert", "args": {"table": "notifications",
                        "record": {"id": 8102, "person": owner, "message": msg_b,
                                   "kind": "warning"}}},
        "verify": {"table": "events", "where": {"title": title}},
    }
    exp_status = "confirmed" if eff_branch == "A" else "needs_review"
    exp_kind = "confirmation" if eff_branch == "A" else "warning"
    terminal = [
        {"type": "field_cmp", "table": "events", "where": {"title": title, "date": date},
         "field": "status", "op": "==", "value": exp_status},
        {"type": "exists", "table": "notifications",
         "where": {"person": owner, "kind": exp_kind}},
    ]
    if near_miss:
        roles = p3_roles(
            {"children": "attendees", "done_word": "accepted", "open_word": "declined",
             "conseq_nm": "set the event status to 'confirmed' and send the owner a 'confirmation' notification",
             "alt_nm": "set it to 'needs_review' and send a 'warning' notification instead",
             "goal": "Finalize the event from the request according to its RSVP list.",
             "parent_phrase": "the event title", "child_table": "attendees",
             "parent_table": "events", "log_table": "notifications",
             "postcond": "The event status and the owner's notification match the RSVP situation."},
            True)
        rule = ("If at least one attendee of the event '%s' (%s) has accepted, set the "
                "event status to 'confirmed' and insert a 'confirmation' notification for "
                "the owner (use id 8101); otherwise set it to 'needs_review' and insert a "
                "'warning' notification (id 8102)." % (title, date))
    else:
        roles = p3_roles(
            {"children": "attendees", "done_word": "accepted", "open_word": "declined",
             "conseq": "set the event status to 'confirmed' and send the owner a 'confirmation' notification",
             "alt": "set it to 'needs_review' and send a 'warning' notification instead",
             "goal": "Finalize the event from the request once nobody has declined.",
             "parent_phrase": "the event title", "child_table": "attendees",
             "parent_table": "events", "log_table": "notifications",
             "postcond": "The event is confirmed exactly when no attendee declined, with a matching owner notification."},
            False)
        rule = ("If no attendee of the event '%s' (%s) has declined (their RSVP count of "
                "'declined' is 0), set the event status to 'confirmed' and insert a "
                "'confirmation' notification addressed to the event's owner (use id 8101); "
                "otherwise set it to 'needs_review' and insert a 'warning' notification "
                "(id 8102)." % (title, date))
    if style == 0:
        instr = ("Calendar operations request. The event '%s' on %s is in the events "
                 "table; its invitees are in the attendees table. Policy: %s Look up the "
                 "event, count the RSVPs yourself, then write the status and the "
                 "notification for the event owner (%s)." % (title, date, rule, owner))
    elif style == 1:
        instr = ("Hi! Could you finalize '%s' scheduled for %s? %s The attendees table "
                 "has the RSVP list; the owner is %s. Please aggregate the responses "
                 "first, then write both records. Thanks!" % (title, date, rule, owner))
    else:
        instr = ("Ops note: finalize event '%s' (%s).\nPolicy: %s\nCount RSVPs first, "
                 "then write the event status and the owner notification (%s)."
                 % (title, date, rule, owner))
    return finish_instance(
        "aggregate_gate", tables, program_params, {"branch": eff_branch},
        terminal, roles, instr,
        {"title": title, "date": date, "owner": owner, "n_att": n_att,
         "dec_n": dec_n, "acc_n": acc_n, "n_distractors": n_dis})


# ===========================================================================
# P4 delete_after_capture: crm_purge_lead / ticket_purge_spam
#   READ target ; CHECK guard ; WRITE archive-insert ; WRITE delete children
#   ; WRITE delete parent (after archive) ; VERIFY
# near-miss: archive step removed (delete without capture -> different class
#            step set AND different safety profile)
# ===========================================================================

def p4_roles(vocab, nm):
    steps = ["Read the %s row for %s." % (vocab["table"], vocab["id_phrase"]),
             "Confirm the row's %s is '%s' -- if it is not, stop without writing."
             % (vocab["guard_field"], vocab["guard_value"])]
    if not nm:
        steps.append("Copy the row into the %s table (%s)."
                     % (vocab["archive_table"], vocab["archive_what"]))
    else:
        steps.append("No archival copy is required for this request.")
    steps += [
        "Delete the linked rows in the %s table." % vocab["child_table"],
        "Delete the %s row itself." % vocab["table"],
        "Read the %s table to confirm before finishing." % (vocab["archive_table"] if not nm else vocab["table"]),
    ]
    return {
        "goal": vocab["goal"],
        "preconds": [
            "The request identifies %s." % vocab["id_phrase"],
            "The row's %s must be '%s'." % (vocab["guard_field"], vocab["guard_value"]),
        ],
        "steps": steps,
        "postconds": [vocab["postcond"]],
        "guards": ([
            "The archival insert MUST happen before any delete; if the insert fails, "
            "do not delete anything.",
        ] if not nm else []) + [
            "Delete only rows matching the exact identifier; never delete in bulk.",
            "Verify the guard field before touching anything.",
        ],
    }


def sample_crm_purge(rng, j):
    return {"arch_date": rng.choice(DATES), "source_bias": rng.choice(SOURCES)}


def build_crm_purge_lead(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "crmpurge"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "crmpurge"))
    used_n, used_e = set(), set()
    name = person(rng_s, used_n)
    email = email_of(rng_s, name, used_e)
    score = rng_s.randint(5, 80)
    arch_id = rng_s.randint(90001, 99999)
    lead = {"id": rng_s.randint(100, 899), "name": name, "email": email,
            "status": "cold", "score": score, "source": prm["source_bias"]}
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    leads = [lead]
    for i in range(n_dis):
        nm_ = person(rng_d, used_n)
        em = email_of(rng_d, nm_, used_e)
        row = {"id": 900 + i, "name": nm_, "email": em,
               "status": rng_d.choice(["cold", "warm", "hot", "archived"]),
               "score": rng_d.randint(0, 100), "source": rng_d.choice(SOURCES)}
        if rng_d.random() < 0.15:
            row["source"] = None           # missing-field injection
        leads.append(row)
    rng_d.shuffle(leads)
    notes = [{"id": 300 + j, "email": email, "note": "call note %d" % j,
              "date": rng_s.choice(DATES)} for j in range(rng_s.randint(1, 3))]
    for i in range(rng_d.randint(3, 9)):
        notes.append({"id": 500 + i, "email": rng_d.choice([r["email"] for r in leads]),
                      "note": "note %d" % i, "date": rng_d.choice(DATES)})
    rng_d.shuffle(notes)
    archived = [{"id": 700 + i, "name": person(rng_d, set()),
                 "email": "old%d@example.com" % i,
                 "status": "cold", "score": rng_d.randint(0, 50),
                 "archived_on": rng_d.choice(DATES)}
                for i in range(rng_d.randint(1, 3))]   # >=1 row: keep columns defined
    tables = {"leads": leads, "lead_notes": notes, "archived_leads": archived}
    archive_rec = {"id": arch_id, "name": name, "email": email, "status": "cold",
                   "score": score, "archived_on": prm["arch_date"]}
    steps_params = {
        "class_tag": "delete_only" if near_miss else "archive_then_delete",
        "skip_archive": near_miss,
        "read": {"table": "leads", "filter": {"email": email}},
        "check": {"kind": "field_cmp", "table": "leads", "where": {"email": email},
                  "field": "status", "op": "==", "value": "cold"},
        "archive": {"tool": "insert", "args": {"table": "archived_leads",
                    "record": archive_rec}},
        "delete_children": {"tool": "delete", "args": {"table": "lead_notes",
                            "where": {"email": email}}},
        "delete_parent": {"tool": "delete", "args": {"table": "leads",
                          "where": {"email": email}}},
        "verify_arch": {"table": "archived_leads" if not near_miss else "leads",
                        "where": {"email": email}},
    }
    terminal = [
        {"type": "not_exists", "table": "leads", "where": {"email": email}},
        {"type": "not_exists", "table": "lead_notes", "where": {"email": email}},
    ]
    if not near_miss:
        terminal += [
            {"type": "exists", "table": "archived_leads", "where": {"email": email}},
            {"type": "field_cmp", "table": "archived_leads", "where": {"email": email},
             "field": "score", "op": "==", "value": score},
        ]
    else:
        terminal.append({"type": "not_exists", "table": "archived_leads",
                         "where": {"email": email}})
    roles = p4_roles(
        {"table": "leads", "id_phrase": "the lead's email address",
         "guard_field": "status", "guard_value": "cold",
         "archive_table": "archived_leads",
         "archive_what": "keep id, name, email, status, score, archived date",
         "child_table": "lead_notes",
         "goal": "Purge the cold lead from the request while preserving an archive copy.",
         "postcond": "The lead and its notes are gone and the archived_leads copy holds "
                     "the original fields."},
        near_miss)
    if near_miss:
        rule = ("If the lead %s (%s) in the leads table has status 'cold', permanently "
                "erase the lead and all of its rows in lead_notes -- no archival copy is "
                "needed. If the status is not 'cold', do nothing.")
    else:
        rule = ("If the lead %s (%s) in the leads table has status 'cold', first archive "
                "it into archived_leads with id %d (copy name, email, status, score, and "
                "use archived_on '%s'), then delete all of its lead_notes rows and finally "
                "delete the lead row itself. If the status is not 'cold', do nothing."
                % (name, email, arch_id, prm["arch_date"]))
    if near_miss:
        rule = rule % (name, email)
    if style == 0:
        instr = ("Data hygiene request. %s Verify the status first, carry out the steps "
                 "in a safe order, and confirm the final state." % rule)
    elif style == 1:
        instr = ("Hi! Could you handle this lead cleanup? %s Please double-check the "
                 "status before deleting anything, and verify afterwards. Thanks!" % rule)
    else:
        instr = ("Ops note: lead cleanup.\n%s\nCheck status, act in a safe order, verify."
                 % rule)
    return finish_instance(
        "delete_after_capture", tables, steps_params, {"branch": "A"},
        terminal, roles, instr,
        {"entity_name": name, "entity_email": email, "score": score,
         "arch_id": arch_id, "n_distractors": n_dis})


def sample_ticket_purge(rng, j):
    return {"prefix": rng.choice(TICKET_PREFIX)}


def build_ticket_purge_spam(fp, sib_idx, state_seed, near_miss, gs, dcfg, style):
    prm = fp["params"]
    rng_s = random.Random(sha_int("sib", gs, fp["idx"], sib_idx, "tickp"))
    rng_d = random.Random(sha_int("state", gs, fp["idx"], sib_idx, state_seed, "tickp"))
    tkey = "%s-%d" % (prm["prefix"], rng_s.randint(1000, 9999))
    title = rng_s.choice(["FREE OFFER click now", "winner notification",
                          "unclaimed prize", "cheap meds online"])
    reporter = person(rng_s, set())
    audit_id = rng_s.randint(60001, 69999)
    ticket = {"id": rng_s.randint(100, 899), "tkey": tkey, "title": title,
              "priority": "p4", "status": "open", "assignee": "spambot-desk",
              "reporter": reporter, "tag": "spam"}
    n_dis = rng_d.randint(dcfg["distractor_rows_min"], dcfg["distractor_rows_max"])
    tickets = [ticket]
    used_keys = {tkey}
    for i in range(n_dis):
        k2 = "%s-%d" % (rng_d.choice(TICKET_PREFIX), rng_d.randint(1000, 9999))
        if k2 in used_keys:
            k2 += "Z"
        used_keys.add(k2)
        tickets.append({"id": 900 + i, "tkey": k2, "title": rng_d.choice(TICKET_TOPICS),
                        "priority": rng_d.choice(["p1", "p2", "p3"]),
                        "status": rng_d.choice(["open", "in_progress", "resolved"]),
                        "assignee": person(rng_d, set()), "reporter": person(rng_d, set()),
                        "tag": rng_d.choice(["normal", "vip", "spam"])})
    rng_d.shuffle(tickets)
    subtasks = [{"id": 200 + j, "tkey": tkey, "title": "auto %d" % j,
                 "status": rng_s.choice(["open", "done"])}
                for j in range(rng_s.randint(1, 3))]
    for i in range(rng_d.randint(3, 8)):
        subtasks.append({"id": 400 + i, "tkey": rng_d.choice(list(used_keys - {tkey})),
                         "title": "sub %d" % i, "status": rng_d.choice(["done", "open"])})
    rng_d.shuffle(subtasks)
    events = [{"id": 800 + i, "tkey": rng_d.choice(list(used_keys - {tkey})),
               "etype": rng_d.choice(["comment", "audit"]),
               "note": "existing log"} for i in range(rng_d.randint(2, 6))]
    tables = {"tickets": tickets, "subtasks": subtasks, "ticket_events": events}
    audit_note = "Archived spam ticket %s: '%s' (reporter %s)." % (tkey, title, reporter)
    steps_params = {
        "class_tag": "delete_only" if near_miss else "archive_then_delete",
        "skip_archive": near_miss,
        "read": {"table": "tickets", "filter": {"tkey": tkey}},
        "check": {"kind": "field_cmp", "table": "tickets", "where": {"tkey": tkey},
                  "field": "tag", "op": "==", "value": "spam"},
        "archive": {"tool": "insert", "args": {"table": "ticket_events",
                    "record": {"id": audit_id, "tkey": tkey, "etype": "audit",
                               "note": audit_note}}},
        "delete_children": {"tool": "delete", "args": {"table": "subtasks",
                            "where": {"tkey": tkey}}},
        "delete_parent": {"tool": "delete", "args": {"table": "tickets",
                          "where": {"tkey": tkey}}},
        "verify_arch": {"table": "ticket_events" if not near_miss else "tickets",
                        "where": ({"tkey": tkey, "etype": "audit"} if not near_miss
                                  else {"tkey": tkey})},
    }
    terminal = [
        {"type": "not_exists", "table": "tickets", "where": {"tkey": tkey}},
        {"type": "not_exists", "table": "subtasks", "where": {"tkey": tkey}},
    ]
    if not near_miss:
        terminal.append({"type": "exists", "table": "ticket_events",
                         "where": {"tkey": tkey, "etype": "audit"}})
    else:
        terminal.append({"type": "not_exists", "table": "ticket_events",
                         "where": {"tkey": tkey, "etype": "audit"}})
    roles = p4_roles(
        {"table": "tickets", "id_phrase": "the ticket key",
         "guard_field": "tag", "guard_value": "spam",
         "archive_table": "ticket_events",
         "archive_what": "write an 'audit' entry capturing the key, title and reporter",
         "child_table": "subtasks",
         "goal": "Remove the spam ticket from the request while keeping an audit trail.",
         "postcond": "The ticket and its subtasks are gone and an 'audit' entry remains "
                     "in ticket_events."},
        near_miss)
    if near_miss:
        rule = ("If the ticket %s in the tickets table is tagged 'spam', permanently "
                "erase the ticket and all of its subtasks -- do NOT leave any audit "
                "entry. If it is not tagged 'spam', do nothing." % tkey)
    else:
        rule = ("If the ticket %s in the tickets table is tagged 'spam', first insert an "
                "'audit' entry into ticket_events with id %d capturing the key, title and "
                "reporter, then delete all of its subtasks, and finally delete the ticket "
                "itself. If it is not tagged 'spam', do nothing." % (tkey, audit_id))
    if style == 0:
        instr = ("Abuse desk request. %s Verify the tag yourself before writing, keep the "
                 "order safe, and confirm the final state." % rule)
    elif style == 1:
        instr = ("Hi! Please deal with this spam report (%s). %s Double-check the tag "
                 "before you delete anything, and verify afterwards. Thanks!" % (title, rule))
    else:
        instr = ("Ops note: spam cleanup for %s.\n%s\nCheck the tag, act in a safe order, "
                 "verify." % (title, rule))
    return finish_instance(
        "delete_after_capture", tables, steps_params, {"branch": "A"},
        terminal, roles, instr,
        {"tkey": tkey, "title": title, "reporter": reporter, "audit_id": audit_id,
         "n_distractors": n_dis})


# ---------------------------------------------------------------------------
# registry of the 8 schemas
# ---------------------------------------------------------------------------

SCHEMA_LIST = [
    {"key": "crm_escalate", "domain": "crm", "archetype": "conditional_write",
     "sample": sample_crm_escalate, "build": build_crm_escalate, "j_levels": [1, 2]},
    {"key": "inv_overstock", "domain": "inventory", "archetype": "conditional_write",
     "sample": sample_inv_overstock, "build": build_inv_overstock, "j_levels": [1, 2]},
    {"key": "inv_transfer", "domain": "inventory", "archetype": "two_row_transfer",
     "sample": sample_inv_transfer, "build": build_inv_transfer, "j_levels": [1]},
    {"key": "cal_move_headcount", "domain": "calendar", "archetype": "two_row_transfer",
     "sample": sample_cal_move, "build": build_cal_move_headcount, "j_levels": [1]},
    {"key": "ticket_gate_close", "domain": "ticket", "archetype": "aggregate_gate",
     "sample": sample_ticket_gate, "build": build_ticket_gate_close, "j_levels": [1]},
    {"key": "cal_finalize", "domain": "calendar", "archetype": "aggregate_gate",
     "sample": sample_cal_finalize, "build": build_cal_finalize, "j_levels": [1]},
    {"key": "crm_purge_lead", "domain": "crm", "archetype": "delete_after_capture",
     "sample": sample_crm_purge, "build": build_crm_purge_lead, "j_levels": [1]},
    {"key": "ticket_purge_spam", "domain": "ticket", "archetype": "delete_after_capture",
     "sample": sample_ticket_purge, "build": build_ticket_purge_spam, "j_levels": [1]},
]
SCHEMAS = {s["key"]: s for s in SCHEMA_LIST}


# ===========================================================================
# candidate memory cards (SPEC section 4)
# ===========================================================================

HEADER_LINE = "Retrieved experience - episode outcome: SUCCESS."

STYLE_NAMES = ["formal_sop", "runbook_bullets", "postmortem", "terse_note",
               "training_qa", "checklist"]


def _num(items, fmt="%d. %s"):
    return "\n".join(fmt % (i + 1, x) for i, x in enumerate(items))


def _bul(items, pre="- "):
    return "\n".join(pre + x for x in items)


def render_style0(r):  # formal SOP
    return ("%s\nObjective: %s\nPreconditions:\n%s\nProcedure:\n%s\n"
            "Postconditions:\n%s\nFailure guards:\n%s"
            % (HEADER_LINE, r["goal"], _num(r["preconds"]), _num(r["steps"]),
               _bul(r["postconds"]), _bul(r["guards"])))


def render_style1(r):  # runbook bullets
    return ("%s\n* Goal: %s\n* Requires:\n%s\n* Steps:\n%s\n* Done when:\n%s\n"
            "* Watch out:\n%s"
            % (HEADER_LINE, r["goal"], _bul(r["preconds"], "  - "),
               _bul(r["steps"], "  - "), _bul(r["postconds"], "  - "),
               _bul(r["guards"], "  - ")))


def render_style2(r):  # postmortem prose
    steps = " ".join("Step %d: %s" % (i + 1, x) for i, x in enumerate(r["steps"]))
    pre = " ".join(r["preconds"])
    guards = " ".join(r["guards"])
    return ("%s\nIn a past episode we handled this request: %s Before starting, "
            "we made sure that: %s This is how the episode went. %s In the end, "
            "this held: %s For future runs, keep these guards in mind: %s"
            % (HEADER_LINE, r["goal"], pre, steps, " ".join(r["postconds"]), guards))


def render_style3(r):  # terse ops note
    return ("%s\nGOAL: %s\nREQ: %s\nDO: %s\nDONE WHEN: %s\nNEVER: %s"
            % (HEADER_LINE, r["goal"], " / ".join(r["preconds"]),
               " > ".join(r["steps"]), " / ".join(r["postconds"]),
               " / ".join(r["guards"])))


def render_style4(r):  # training Q&A
    return ("%s\nQ: What is the task? A: %s\nQ: What must be true first? A: %s\n"
            "Q: How do we do it? A: %s\nQ: How do we know it worked? A: %s\n"
            "Q: What can go wrong? A: %s"
            % (HEADER_LINE, r["goal"], " ".join(r["preconds"]),
               " ".join(r["steps"]), " ".join(r["postconds"]),
               " ".join(r["guards"])))


def render_style5(r):  # checklist
    items = (["confirm: %s" % p for p in r["preconds"]] +
             ["do: %s" % s for s in r["steps"]] +
             ["verify: %s" % p for p in r["postconds"]])
    return ("%s\nChecklist for: %s\n%s\nReminders:\n%s"
            % (HEADER_LINE, r["goal"], _bul(items, "[ ] "), _bul(r["guards"])))


CARD_STYLES = [render_style0, render_style1, render_style2, render_style3,
               render_style4, render_style5]


def roles_core(roles):
    """Content core of a memory card (goal/procedure/postconditions), without
    style boilerplate and length-matching filler. Embedding similarity is
    computed on this text so the calibration measures the memory's actual
    content, not shared card formatting (see README, S operationalisation)."""
    return " ".join([roles["goal"]] + list(roles["steps"])
                    + list(roles["postconds"]))

# task-irrelevant procedures for the Q (sham / placebo) cell: same schema,
# same success tag, matched length -- zero task-related content.
SHAM_ROLES = [
    {"goal": "Cook a pot of plain rice on the stove.",
     "preconds": ["You have rice, water, a pot with a lid, and a stove."],
     "steps": ["Rinse the rice under cold water until the water runs mostly clear.",
               "Add one part rice and two parts water to the pot.",
               "Bring to a boil, then reduce to low heat and cover with the lid.",
               "Simmer for fifteen minutes without lifting the lid.",
               "Turn off the heat and let it rest for five minutes.",
               "Fluff the rice with a fork before serving."],
     "postconds": ["The rice is tender and the water is fully absorbed."],
     "guards": ["Never leave the stove unattended.",
                "If the water boils over, lower the heat at once.",
                "Do not lift the lid during the simmering phase."]},
    {"goal": "Repot a houseplant into a larger container.",
     "preconds": ["The new pot is one size up and has drainage holes.",
                  "Fresh potting soil is available."],
     "steps": ["Water the plant a few hours before repotting.",
               "Fill the new pot one third with fresh soil.",
               "Tip the old pot sideways and slide the root ball out gently.",
               "Loosen circling roots with your fingers.",
               "Set the plant in the new pot and fill gaps with soil.",
               "Water lightly and place it in indirect light for a week."],
     "postconds": ["The plant stands upright and the soil is evenly moist."],
     "guards": ["Do not pull the plant by its stem.",
                "Stop if the root ball crumbles; add soil to stabilize instead.",
                "Avoid direct sun for the first week."]},
    {"goal": "Brew a cup of pour-over coffee.",
     "preconds": ["You have ground coffee, a filter, a dripper, and hot water."],
     "steps": ["Place the filter in the dripper and rinse it with hot water.",
               "Add two tablespoons of ground coffee.",
               "Bloom the grounds with a small amount of water for thirty seconds.",
               "Pour the remaining water in slow circles over the coffee bed.",
               "Let the coffee drain fully into the cup."],
     "postconds": ["The cup holds clear coffee without grounds."],
     "guards": ["Water should be just off the boil, not violently bubbling.",
                "Pour slowly to avoid overflowing the dripper.",
                "Discard the rinse water before brewing."]},
    {"goal": "Wash a car by hand.",
     "preconds": ["The car is parked in shade and the paint is cool to touch."],
     "steps": ["Rinse the whole car with water to remove loose dirt.",
               "Wash one panel at a time with a mitt and car shampoo.",
               "Clean the wheels last with a separate brush.",
               "Rinse the car thoroughly from top to bottom.",
               "Dry with a clean microfiber towel."],
     "postconds": ["The paint is free of dirt and water spots."],
     "guards": ["Never wash in direct sun; soap dries and stains.",
                "Do not use dish detergent on paint.",
                "Rinse the mitt often to avoid scratching."]},
    {"goal": "Sharpen a kitchen knife on a whetstone.",
     "preconds": ["The whetstone has soaked in water for ten minutes."],
     "steps": ["Place the stone on a damp towel so it cannot slip.",
               "Hold the blade at a steady angle against the stone.",
               "Draw the blade across the stone from heel to tip.",
               "Repeat on both sides the same number of strokes.",
               "Rinse the blade and test it on a sheet of paper."],
     "postconds": ["The edge slices paper cleanly without tearing."],
     "guards": ["Keep fingers behind the blade edge at all times.",
                "Keep the stone wet throughout.",
                "Do not change the angle midway through a stroke."]},
    {"goal": "Pack a hiking backpack for a day trip.",
     "preconds": ["You have a list of water, food, clothing, and safety items."],
     "steps": ["Place heavy items close to the back panel.",
               "Put water bottles in the side pockets.",
               "Keep rain gear and the first aid kit at the top.",
               "Pack snacks in the hip belt pockets.",
               "Tighten all straps and check the total weight."],
     "postconds": ["The pack carries its weight on the hips, not the shoulders."],
     "guards": ["Never skip the first aid kit.",
                "Do not hang loose items outside the pack.",
                "Recheck the weather forecast before leaving."]},
    {"goal": "Edit a portrait photo for natural skin tones.",
     "preconds": ["You have the raw photo and a photo editor with curves."],
     "steps": ["Correct the white balance on a neutral area.",
               "Recover clipped highlights before touching shadows.",
               "Apply gentle contrast with a tone curve.",
               "Reduce saturation slightly in the reds and oranges.",
               "Zoom to full size and remove small blemishes.",
               "Export at the target size without recompressing twice."],
     "postconds": ["Skin looks natural and detail is preserved."],
     "guards": ["Work on a copy; never edit the original file.",
                "Avoid heavy smoothing that destroys texture.",
                "Check the result on a second screen if possible."]},
    {"goal": "Organize a shared bookshelf by topic.",
     "preconds": ["All books are gathered in one place."],
     "steps": ["Sort the books into topic piles on the floor.",
               "Declutter duplicates and damaged copies.",
               "Assign each pile a shelf section.",
               "Order each section by author name.",
               "Label the sections on the shelf edge."],
     "postconds": ["Every book sits in a labeled section."],
     "guards": ["Do not discard a book without asking its owner.",
                "Keep the heaviest books on the lowest shelf.",
                "Leave a little free space on each shelf."]},
]

# task-neutral boilerplate used to length-match cards across cells
FILLERS = [
    "Double-check every identifier against the request before you act on it.",
    "If a tool returns an error, read the message and fix the arguments instead of retrying blindly.",
    "When several rows are returned, narrow the filter until exactly the intended row matches.",
    "Keep the working steps in the same order even when the tool output is verbose.",
    "Write the final values only after you have seen the current stored values with your own tools.",
    "A quick read-back at the end is cheaper than a wrong write.",
    "Prefer one precise update over several broad ones.",
    "If anything looks inconsistent with the request, stop and report what you found.",
    "Do not assume default values; look them up.",
    "Treat every write as irreversible: confirm the target row first.",
    "Use the exact column names shown by the table listing.",
    "Small arithmetic on retrieved numbers should be done carefully, digit by digit.",
    "The episode is only done once the stored state matches the request.",
    "Ignore rows that merely look similar to the target row.",
    "Names and identifiers in different requests repeat often; the filter decides, not memory of them.",
    "Stay within the requested scope; do not touch unrelated records.",
    "If a value is missing, say so instead of inventing it.",
    "Count carefully when the request depends on how many rows match.",
]

TOOL_SCHEMA_DOC = {
    "description": "RelationalOps tool protocol. Every action is a single JSON object "
                   "{\"tool\": <name>, \"args\": {...}}.",
    "tools": [
        {"name": "list_tables", "args": {},
         "doc": "List tables with their columns."},
        {"name": "read", "args": {"table": "str", "filter": {"col": "value"}, "limit": "int (optional, default 50)"},
         "doc": "Read rows matching equality filters. A filter value may be null or "
                "{\"$ne\": v, \"$lt\": v, \"$le\": v, \"$gt\": v, \"$ge\": v}."},
        {"name": "aggregate", "args": {"table": "str", "agg": "count|sum|min|max|avg",
                                       "field": "str (required unless count)", "filter": "optional"},
         "doc": "Aggregate over filtered rows."},
        {"name": "insert", "args": {"table": "str", "record": {"col": "value"}},
         "doc": "Insert one row."},
        {"name": "update", "args": {"table": "str", "set": {"col": "value"}, "where": {"col": "value"}},
         "doc": "Update rows matching where; where must be non-empty."},
        {"name": "delete", "args": {"table": "str", "where": {"col": "value"}},
         "doc": "Delete rows matching where; where must be non-empty."},
        {"name": "finish", "args": {"answer": "str"},
         "doc": "End the episode once the required final state is reached."},
    ],
}


# ---------------------------------------------------------------------------
# token measurement + length matching
# ---------------------------------------------------------------------------

class TokenMeter:
    def __init__(self, tokenizer_name):
        from transformers import AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(tokenizer_name)

    def count(self, text):
        return len(self.tok.encode(text))


def pad_to_tokens(text, meter, rng, target, min_t, max_t):
    fillers = FILLERS[:]
    rng.shuffle(fillers)
    out = text
    i = 0
    while meter.count(out) < target and i < len(fillers):
        out = out + "\nNote: " + fillers[i]
        i += 1
    n = meter.count(out)
    if n < min_t or n > max_t:
        raise RuntimeError("card length %d outside [%d, %d] even after padding"
                           % (n, min_t, max_t))
    return out, n


# ---------------------------------------------------------------------------
# similarity metrics + S-bucket verification (SPEC 4, tech report 6.9-5)
# ---------------------------------------------------------------------------

class Embedder:
    def __init__(self, model_names, device):
        from sentence_transformers import SentenceTransformer
        last = None
        for name in model_names:
            if os.environ.get("EMBEDDER_DEBUG"):
                self.model = SentenceTransformer(name, device=device)
                self.name = name
                return
            try:
                self.model = SentenceTransformer(name, device=device)
                self.name = name
                return
            except Exception as e:
                print("[gen] embedding model %s failed to load: %s: %s"
                      % (name, type(e).__name__, str(e)[:200]), flush=True)
                last = e
        raise RuntimeError("could not load any embedding model: %s" % last)

    def cos(self, a, b):
        import numpy as np
        v = self.model.encode([a, b], normalize_embeddings=True)
        return float(np.dot(v[0], v[1]))


# forbidden tokens in agent-visible files (ORACLE ISOLATION automated check).
# Two passes: case-insensitive vocabulary, and case-SENSITIVE cell labels with
# word boundaries so lowercase hex in opaque ids cannot false-positive.
FORBIDDEN_RE_CI = re.compile(
    r"family_id|cell_id|families|family|\bcell\b|near.?miss|archetype|oracle|"
    r"sealed|evaluator|transformation|treatment|\bP=|\bS=", re.IGNORECASE)
FORBIDDEN_RE_CS = re.compile(r"\bA00\b|\bA01\b|\bA10\b|\bA11\b")


def isolation_scan(public_dir):
    hits = []
    for root, _, files in os.walk(public_dir):
        for fn in files:
            p = os.path.join(root, fn)
            with open(p, errors="replace") as f:
                txt = f.read()
            for rx in (FORBIDDEN_RE_CI, FORBIDDEN_RE_CS):
                for m in rx.finditer(txt):
                    line_no = txt[:m.start()].count("\n") + 1
                    hits.append((p, line_no, m.group(0)))
    return hits


# ---------------------------------------------------------------------------
# family planning
# ---------------------------------------------------------------------------

def plan_families(cfg):
    """40 families: 5 per schema (interleaved). P1 schemas split join depth:
    crm_escalate [J1 x3, J2 x2], inv_overstock [J1 x2, J2 x3], so every
    P1 class has families in both domains (required for A10 pairing)."""
    gcfg = cfg["generation"]
    n = gcfg["n_families"]
    gs = gcfg["generator_seed"]
    j_split = {"crm_escalate": [1, 1, 1, 2, 2], "inv_overstock": [1, 1, 2, 2, 2]}
    fams = []
    for i in range(n):
        smeta = SCHEMA_LIST[i % len(SCHEMA_LIST)]
        occ = i // len(SCHEMA_LIST)
        rngf = random.Random(sha_int("fam", gs, i))
        if smeta["key"] in j_split:
            j = j_split[smeta["key"]][occ % len(j_split[smeta["key"]])]
        else:
            j = smeta["j_levels"][0]
        params = smeta["sample"](rngf, j)
        fams.append({"idx": i, "schema_key": smeta["key"], "domain": smeta["domain"],
                     "archetype": smeta["archetype"], "params": params,
                     "occ": occ})
    return fams


def build_instances_for_family(cfg, fam):
    smeta = SCHEMAS[fam["schema_key"]]
    gcfg = cfg["generation"]
    gs = gcfg["generator_seed"]
    dcfg = gcfg
    insts = {}
    n_sib = gcfg["siblings_per_family"]
    for s in range(n_sib):
        style = (fam["idx"] + s) % 3
        for seed in gcfg["state_seeds"]:
            insts[("sibling", s, seed)] = smeta["build"](fam, s, seed, False,
                                                         gs, dcfg, style)
    nm_style = fam["idx"] % 3
    for seed in gcfg["state_seeds"]:
        insts[("near_miss", 0, seed)] = smeta["build"](fam, 90, seed, True,
                                                       gs, dcfg, nm_style)
    return insts


# ---------------------------------------------------------------------------
# writers
# ---------------------------------------------------------------------------

def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)


def write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


CELL_RANK = {"A00": 0, "A01": 1, "A10": 2, "A11": 3, "Q": 4}
MEMORY_CELLS = ["A00", "A01", "A10", "A11", "Q"]


# ---------------------------------------------------------------------------
# main pipeline
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "configs", "pilot.yaml"))
    ap.add_argument("--skip-embedding", action="store_true",
                    help="degraded mode: skip embedding similarity (token "
                         "overlap still enforced). Not for final generation.")
    args = ap.parse_args()
    cfg = load_config(args.config)
    gcfg = cfg["generation"]
    mcfg = cfg["memories"]
    gs = gcfg["generator_seed"]
    cfg["_gs"] = gs
    pub = cfg["paths"]["public_view"]
    sealed = cfg["paths"]["sealed"]
    log_dir = cfg["paths"]["log_root"]
    os.makedirs(log_dir, exist_ok=True)
    t0 = time.time()

    print("[gen] planning families ...")
    fams = plan_families(cfg)
    print("[gen] %d families planned across %d schemas" % (len(fams), len(SCHEMA_LIST)))

    # ---- build all task instances --------------------------------------
    print("[gen] building task instances (siblings + near-miss, %d seeds) ..."
          % len(gcfg["state_seeds"]))
    all_insts = {}     # fam_idx -> {(kind, sib, seed) -> instance}
    for fam in fams:
        all_insts[fam["idx"]] = build_instances_for_family(cfg, fam)

    # ---- class map + A10/A00 pairing ------------------------------------
    sig = {}
    for fam in fams:
        sig[fam["idx"]] = all_insts[fam["idx"]][("sibling", 0, 0)]["signature"]
    by_class = defaultdict(list)
    for fidx, s in sig.items():
        by_class[s].append(fidx)
    a10_partner, a00_partner = {}, {}
    for fam in fams:
        cands = [x for x in by_class[sig[fam["idx"]]]
                 if fams[x]["domain"] != fam["domain"]]
        if not cands:
            raise RuntimeError("no cross-domain partner for family %d (%s)"
                               % (fam["idx"], sig[fam["idx"]]))
        a10_partner[fam["idx"]] = sorted(cands)[fam["occ"] % len(cands)]
        cands00 = [x for x in range(len(fams))
                   if sig[x] != sig[fam["idx"]] and fams[x]["domain"] != fam["domain"]]
        if not cands00:
            raise RuntimeError("no unrelated partner for family %d" % fam["idx"])
        a00_partner[fam["idx"]] = cands00[(fam["idx"] * 7 + 3) % len(cands00)]

    # ---- candidate memories ----------------------------------------------
    print("[gen] loading tokenizer %s ..." % mcfg["tokenizer"])
    meter = TokenMeter(mcfg["tokenizer"])
    memories = []       # sealed rows
    n_sib = gcfg["siblings_per_family"]
    for fam in fams:
        fidx = fam["idx"]
        roles_sib = all_insts[fidx][("sibling", 0, 0)]["roles"]
        roles_nm = all_insts[fidx][("near_miss", 0, 0)]["roles"]
        roles_a10 = all_insts[a10_partner[fidx]][("sibling", 0, 0)]["roles"]
        roles_a00 = all_insts[a00_partner[fidx]][("sibling", 0, 0)]["roles"]
        for s in range(n_sib):
            for cell in MEMORY_CELLS:
                rank = CELL_RANK[cell]
                style_idx = (fidx * n_sib + s + rank) % len(CARD_STYLES)
                rngc = random.Random(sha_int("card", gs, fidx, s, cell))
                if cell == "A11":
                    roles, src, src_fam, P, S = roles_sib, "sibling_same_family", fidx, 1, 1
                elif cell == "A10":
                    roles, src, src_fam, P, S = roles_a10, "cross_domain_pair", a10_partner[fidx], 1, 0
                elif cell == "A01":
                    roles, src, src_fam, P, S = roles_nm, "near_miss", fidx, 0, 1
                elif cell == "A00":
                    roles, src, src_fam, P, S = roles_a00, "unrelated", a00_partner[fidx], 0, 0
                else:
                    roles, src, src_fam, P, S = (SHAM_ROLES[(fidx + s) % len(SHAM_ROLES)],
                                                 "sham", None, None, None)
                base = CARD_STYLES[style_idx](roles)
                mid = opaque_id("m", gs, fidx, s, cell)
                text, ntok = pad_to_tokens(base, meter, rngc, mcfg["tokens_target"],
                                           mcfg["tokens_min"], mcfg["tokens_max"])
                memories.append({
                    "memory_id": mid, "family_idx": fidx, "target_sibling": s,
                    "cell": cell, "P": P, "S": S, "source_kind": src,
                    "source_family": src_fam, "style_idx": style_idx,
                    "style_name": STYLE_NAMES[style_idx], "token_count": ntok,
                    "embed_core": roles_core(roles),
                    "text": text})
    print("[gen] %d candidate memories built; token range [%d, %d]"
          % (len(memories),
             min(m["token_count"] for m in memories),
             max(m["token_count"] for m in memories)))
    # Latin-square balance record
    style_balance = {c: Counter() for c in MEMORY_CELLS}
    for m in memories:
        style_balance[m["cell"]][m["style_name"]] += 1
    for c in MEMORY_CELLS:
        counts = style_balance[c]
        assert max(counts.values()) - min(counts.values()) <= 2, \
            "style template imbalance in %s: %s" % (c, counts)

    # ---- S calibration (token overlap mandatory, embedding optional) -----
    hi_tf = gcfg["sim_token_overlap_high"]
    lo_tf = gcfg["sim_token_overlap_low"]
    hi_em = gcfg["sim_embed_high"]
    lo_em = gcfg["sim_embed_low"]
    embedder = None
    if not args.skip_embedding:
        print("[gen] loading embedding model (cpu; first run downloads ~100MB) ...")
        embedder = Embedder([gcfg["embed_model"], gcfg["embed_fallback_model"]],
                            gcfg["embed_device"])
        print("[gen] embedding model: %s" % embedder.name)
    sim_rows, violations = [], []
    for m in memories:
        fam = fams[m["family_idx"]]
        instr = all_insts[m["family_idx"]][("sibling", m["target_sibling"], 0)]["instruction"]
        tf = tf_cosine(m["text"], instr)
        em = embedder.cos(m["embed_core"], instr) if embedder else None
        m["sim_tf"] = round(tf, 4)
        m["sim_embed"] = round(em, 4) if em is not None else None
        sim_rows.append({"memory_id": m["memory_id"], "family_idx": m["family_idx"],
                         "target_sibling": m["target_sibling"], "cell": m["cell"],
                         "P": m["P"], "S": m["S"], "sim_tf": m["sim_tf"],
                         "sim_embed": m["sim_embed"]})
        want_high = m["S"] == 1
        want_low = m["S"] == 0
        if want_high and not (tf >= hi_tf):
            violations.append((m, "expected HIGH bucket (tf)", tf, em))
        if want_low and not (tf <= lo_tf):
            violations.append((m, "expected LOW bucket (tf)", tf, em))
    if violations:
        os.makedirs(sealed, exist_ok=True)
        _write_sim_csv(os.path.join(sealed, "sim_report.csv"), sim_rows)
        for v in violations[:20]:
            print("[gen] BUCKET VIOLATION: fam %d sib %d cell %s: %s (tf=%.3f emb=%s)"
                  % (v[0]["family_idx"], v[0]["target_sibling"], v[0]["cell"],
                     v[1], v[2], ("%.3f" % v[3]) if v[3] is not None else "null"))
        raise SystemExit("[gen] %d similarity bucket violations; adjust text or "
                         "thresholds in config" % len(violations))

    # Embedding-metric calibration (dual-metric S operationalisation).
    # Frozen encoders conflate surface and PROGRAM similarity (same-archetype
    # cross-domain pairs embed close by design), so a razor-thin boundary band
    # is physically unavoidable; lexical token overlap is therefore the
    # bucket-DEFINING metric (hard per-pair gate above), and the embedding
    # metric is calibrated at the distribution level: per-cell medians must
    # lie on the correct side of the config anchors, and the residual number
    # of pairs inside the boundary band is reported as data (feeds the
    # continuous-S sensitivity analysis in Loop Step 3).
    embed_calibration = None
    if embedder:
        import statistics
        by_cell = {}
        for c in MEMORY_CELLS:
            vs = sorted(m["sim_embed"] for m in memories if m["cell"] == c)
            by_cell[c] = vs
        med = {c: statistics.median(vs) for c, vs in by_cell.items()}
        emb_violations = []
        for c in ("A11", "A01"):
            if med[c] < hi_em:
                emb_violations.append((c, "median %.3f < high anchor %.3f" % (med[c], hi_em)))
        for c in ("A10", "A00"):
            if med[c] > lo_em:
                emb_violations.append((c, "median %.3f > low anchor %.3f" % (med[c], lo_em)))
        if emb_violations:
            raise SystemExit("[gen] embedding calibration failed: %s" % emb_violations)
        n_hi_below = sum(1 for m in memories if m["S"] == 1 and m["sim_embed"] < hi_em)
        n_lo_above = sum(1 for m in memories if m["S"] == 0 and m["sim_embed"] > lo_em)
        embed_calibration = {
            "cell_medians": {c: round(v, 4) for c, v in med.items()},
            "cell_min": {c: round(min(vs), 4) for c, vs in by_cell.items()},
            "cell_max": {c: round(max(vs), 4) for c, vs in by_cell.items()},
            "anchors": {"high": hi_em, "low": lo_em},
            "boundary_overlap": {"s1_pairs_below_high_anchor": n_hi_below,
                                 "s0_pairs_above_low_anchor": n_lo_above},
        }
        print("[gen] embedding calibration: medians %s; boundary overlap %s"
              % (embed_calibration["cell_medians"], embed_calibration["boundary_overlap"]))

    # ---- oracle validation (tech report 6.9-1: 100% legal terminal) -----
    print("[gen] validating oracle plans on every task instance ...")
    oracle_rows, n_fail = [], 0
    for fam in fams:
        for (kind, sib, seed), inst in all_insts[fam["idx"]].items():
            env = RelationalOpsEnv(inst["tables"], inst["terminal"])
            prog = ARCHETYPES[fam["archetype"]](inst["program_params"])
            ok, detail = run_oracle_plan(env, prog, inst["plan"])
            oracle_rows.append({"family_idx": fam["idx"], "kind": kind,
                                "sibling": sib, "seed": seed, "ok": ok,
                                "detail": None if ok else detail.get("error")})
            if not ok:
                n_fail += 1
                print("[gen] ORACLE FAILURE fam %d %s sib %d seed %d: %s"
                      % (fam["idx"], kind, sib, seed, detail.get("error")))
    oracle_report = {"checked": len(oracle_rows),
                     "ok": sum(1 for r in oracle_rows if r["ok"]),
                     "failures": [r for r in oracle_rows if not r["ok"]]}
    print("[gen] oracle validation: %d/%d instances reach a legal terminal state"
          % (oracle_report["ok"], oracle_report["checked"]))
    if n_fail:
        write_json(os.path.join(sealed, "oracle_report.json"), oracle_report)
        raise SystemExit("[gen] oracle validation failed on %d instances; "
                         "fix the generator before proceeding" % n_fail)

    # ---- write public view (agent-visible, label-free) -------------------
    print("[gen] writing public view ...")
    task_rows_pub = []
    sealed_task_rows = []
    used_tids = set()
    for fam in fams:
        for (kind, sib, seed), inst in sorted(all_insts[fam["idx"]].items()):
            tid = opaque_id("t", gs, fam["idx"], kind, sib, seed)
            assert tid not in used_tids
            used_tids.add(tid)
            write_json(os.path.join(pub, "tasks", tid + ".json"),
                       {"task_id": tid, "instruction": inst["instruction"],
                        "tables": inst["tables"]})
            digest = hashlib.sha1(json.dumps(inst["tables"], sort_keys=True).encode()).hexdigest()[:12]
            sealed_task_rows.append({
                "task_id": tid, "family_idx": fam["idx"], "kind": kind,
                "sibling_idx": sib, "seed": seed,
                "schema_key": fam["schema_key"], "domain": fam["domain"],
                "signature": inst["signature"], "branch": inst["binding"]["branch"],
                "instruction": inst["instruction"],
                "program_params": inst["program_params"],
                "terminal": inst["terminal"], "oracle_plan": inst["plan"],
                "tables_digest": digest, "meta": inst["meta"]})
    write_json(os.path.join(pub, "tool_schema.json"), TOOL_SCHEMA_DOC)
    mem_ids = set()
    for m in memories:
        assert m["memory_id"] not in mem_ids
        mem_ids.add(m["memory_id"])
        write_json(os.path.join(pub, "memories", m["memory_id"] + ".json"),
                   {"memory_id": m["memory_id"], "text": m["text"]})

    # ---- isolation scan (must be clean) ----------------------------------
    print("[gen] running oracle-isolation scan on public view ...")
    hits = isolation_scan(pub)
    if hits:
        for h in hits[:20]:
            print("[gen] ISOLATION VIOLATION: %s:%d matched %r" % h)
        raise SystemExit("[gen] %d isolation violations in public view" % len(hits))

    # ---- sealed writes ----------------------------------------------------
    fam_rows = []
    for fam in fams:
        fam_rows.append({"family_idx": fam["idx"], "schema_key": fam["schema_key"],
                         "domain": fam["domain"], "archetype": fam["archetype"],
                         "params": fam["params"], "signature": sig[fam["idx"]],
                         "a10_partner": a10_partner[fam["idx"]],
                         "a00_partner": a00_partner[fam["idx"]],
                         "nm_kind": {"conditional_write": "flip_polarity",
                                     "two_row_transfer": "reverse_direction",
                                     "aggregate_gate": "wrong_child_set",
                                     "delete_after_capture": "skip_archive"}[fam["archetype"]]})
    write_jsonl(os.path.join(sealed, "families.jsonl"), fam_rows)
    write_jsonl(os.path.join(sealed, "tasks_sealed.jsonl"), sealed_task_rows)
    write_jsonl(os.path.join(sealed, "memories_sealed.jsonl"),
                [{k: v for k, v in m.items()} for m in memories])
    cells_rows = []
    for fam in fams:
        for s in range(n_sib):
            row = {"family_idx": fam["idx"], "sibling_idx": s, "A11": None,
                   "A10": None, "A01": None, "A00": None, "Q": None, "N": None}
            for m in memories:
                if m["family_idx"] == fam["idx"] and m["target_sibling"] == s:
                    row[m["cell"]] = m["memory_id"]
            cells_rows.append(row)
    write_jsonl(os.path.join(sealed, "cells.jsonl"), cells_rows)
    _write_sim_csv(os.path.join(sealed, "sim_report.csv"), sim_rows)
    write_json(os.path.join(sealed, "oracle_report.json"), oracle_report)

    with open(args.config, "rb") as f:
        config_hash = hashlib.sha1(f.read()).hexdigest()[:12]
    token_stats = {}
    for c in MEMORY_CELLS:
        ts = [m["token_count"] for m in memories if m["cell"] == c]
        token_stats[c] = {"n": len(ts), "mean": sum(ts) / len(ts),
                          "min": min(ts), "max": max(ts)}
    manifest = {
        "created": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.gmtime()),
        "elapsed_sec": round(time.time() - t0, 1),
        "git_commit": git_commit(), "config_hash": config_hash,
        "generator_seed": gs, "n_families": len(fams),
        "siblings_per_family": n_sib, "state_seeds": gcfg["state_seeds"],
        "n_tasks_public": len(used_tids), "n_memories": len(memories),
        "tokenizer": mcfg["tokenizer"],
        "embed_model": (embedder.name if embedder else None),
        "sim_thresholds": {"tf_high": hi_tf, "tf_low": lo_tf,
                           "embed_high": hi_em, "embed_low": lo_em},
        "embed_calibration": embed_calibration,
        "token_stats_by_cell": token_stats,
        "style_balance": {c: dict(style_balance[c]) for c in MEMORY_CELLS},
        "oracle_report": oracle_report,
        "skip_embedding": args.skip_embedding,
    }
    write_json(os.path.join(sealed, "manifest.json"), manifest)
    print("[gen] done in %.1fs: %d tasks, %d memories; sealed manifest at %s"
          % (time.time() - t0, len(used_tids), len(memories),
             os.path.join(sealed, "manifest.json")))
    print("[gen] token stats by cell: %s"
          % json.dumps({c: {"mean": round(v["mean"], 1), "min": v["min"], "max": v["max"]}
                        for c, v in token_stats.items()}, indent=1))


def _write_sim_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["memory_id", "family_idx", "target_sibling",
                                          "cell", "P", "S", "sim_tf", "sim_embed"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
