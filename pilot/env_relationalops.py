"""RelationalOps environment for the CausalMemBench mini-pilot.

A single SQLite (in-memory) state + programmatic tools. One env instance ==
one rollout episode; every rollout deep-copies the tables of its task so no
state leaks between cells (SPEC.md section 2).

Tools (invoked through ``call``):
    list_tables()
    read(table, filter, limit?)
    aggregate(table, agg, field?, filter?)
    insert(table, record)
    update(table, set, where)
    delete(table, where)
    finish(answer)                -- handled by the harness, not the env

Safety constraints enforced at the tool level (part of C_safety):
    * update / delete REQUIRE a non-empty ``where`` (no full-table wipes);
    * unknown table / column names return structured errors (the agent sees
      these and can recover within its step budget).

Terminal success is decided ONLY by programmatic predicates over the DB
(C_terminal). No LLM judge anywhere in the pipeline.
"""

import copy
import sqlite3

_CMP = {"<": lambda a, b: a < b,
        "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b,
        ">=": lambda a, b: a >= b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b}

TOOLS = ["list_tables", "read", "aggregate", "insert", "update", "delete", "finish"]


def _fmterr(argname, val):
    """Corrective format error: teaches the JSON-object convention through
    tool feedback (agents recover from these instead of repeating the error)."""
    if isinstance(val, str):
        got = "a string (%r)" % val[:80]
    else:
        got = type(val).__name__
    return {"error": ("'%s' must be a JSON object mapping column names to "
                      "values, e.g. {\"sku\": \"AB-1\", \"warehouse\": \"east\"}; "
                      "got %s. SQL strings are not supported." % (argname, got))}


def _where_clause(filter):
    """Build (sql_fragment, vals) from a filter dict.
    Values: scalar -> ``col = ?``; None -> ``col IS NULL``;
    {"<op>": v} with op in $ne/$lt/$le/$gt/$ge -> corresponding comparison."""
    _OPS = {"$ne": "!=", "$lt": "<", "$le": "<=", "$gt": ">", "$ge": ">="}
    parts, vals = [], []
    for k, v in (filter or {}).items():
        if isinstance(v, dict):
            if len(v) != 1 or next(iter(v)) not in _OPS:
                raise ValueError("unsupported filter operator in %r" % (v,))
            op = _OPS[next(iter(v))]
            parts.append('"%s" %s ?' % (k, op))
            vals.append(v[next(iter(v))])
        elif v is None:
            parts.append('"%s" IS NULL' % k)
        else:
            parts.append('"%s" = ?' % k)
            vals.append(v)
    return " AND ".join(parts), vals


class RelationalOpsEnv:
    def __init__(self, tables, terminal_predicates=None):
        """tables: {table_name: [row_dict, ...]} (deep-copied internally).
        terminal_predicates: list of concrete predicate dicts."""
        self._tables = copy.deepcopy(tables)
        self._terminal = terminal_predicates or []
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._build()

    # -- construction ------------------------------------------------------
    def _build(self):
        cur = self._conn.cursor()
        self._columns = {}
        for name, rows in self._tables.items():
            cols = []
            for r in rows:
                for k in r:
                    if k not in cols:
                        cols.append(k)
            self._columns[name] = cols
            coldef = ", ".join('"%s"' % c for c in cols)
            cur.execute('CREATE TABLE "%s" (%s)' % (name, coldef))
            for r in rows:
                q = ", ".join("?" for _ in cols)
                cur.execute('INSERT INTO "%s" VALUES (%s)' % (name, q),
                            [r.get(c) for c in cols])
        self._conn.commit()

    def snapshot(self):
        """Deep copy of the current logical state (for diagnostics)."""
        out = {}
        for name in self._tables:
            rows = self._conn.execute('SELECT * FROM "%s"' % name).fetchall()
            out[name] = [dict(r) for r in rows]
        return out

    # -- tools -------------------------------------------------------------
    def list_tables(self):
        return {"tables": [{"name": n, "columns": self._columns[n]}
                           for n in sorted(self._tables)]}

    def read(self, table, filter=None, limit=50):
        err = self._check_table(table)
        if err:
            return err
        if filter is not None and not isinstance(filter, dict):
            return _fmterr("filter", filter)
        filter = filter or {}
        err = self._check_cols(table, filter)
        if err:
            return err
        sql = 'SELECT * FROM "%s"' % table
        vals = []
        if filter:
            w, vals = _where_clause(filter)
            sql += " WHERE " + w
        sql += " LIMIT %d" % int(limit)
        rows = self._conn.execute(sql, vals).fetchall()
        return {"rows": [dict(r) for r in rows], "n": len(rows)}

    def aggregate(self, table, agg, field=None, filter=None):
        err = self._check_table(table)
        if err:
            return err
        agg = (agg or "").lower()
        if filter is not None and not isinstance(filter, dict):
            return _fmterr("filter", filter)
        filter = filter or {}
        err = self._check_cols(table, filter)
        if err:
            return err
        if agg == "count":
            expr = "COUNT(*)"
        elif agg in ("sum", "min", "max", "avg"):
            if not field:
                return {"error": "aggregate %s requires 'field'" % agg}
            err = self._check_cols(table, {field: 0})
            if err:
                return err
            expr = "%s(\"%s\")" % (agg.upper(), field)
        else:
            return {"error": "unknown agg %r (use count|sum|min|max|avg)" % agg}
        sql = 'SELECT %s AS v FROM "%s"' % (expr, table)
        vals = []
        if filter:
            w, vals = _where_clause(filter)
            sql += " WHERE " + w
        v = self._conn.execute(sql, vals).fetchone()["v"]
        return {"value": v}

    def insert(self, table, record):
        err = self._check_table(table)
        if err:
            return err
        if not isinstance(record, dict) or not record:
            return _fmterr("record", record) if not isinstance(record, dict) else \
                {"error": "insert requires a non-empty record dict"}
        err = self._check_cols(table, record)
        if err:
            return err
        cols = list(record)
        sql = 'INSERT INTO "%s" (%s) VALUES (%s)' % (
            table, ", ".join('"%s"' % c for c in cols),
            ", ".join("?" for _ in cols))
        self._conn.execute(sql, [record[c] for c in cols])
        self._conn.commit()
        return {"ok": True, "inserted": 1, "record": record}

    def update(self, table, set, where):
        err = self._check_table(table)
        if err:
            return err
        if not isinstance(set, dict):
            return _fmterr("set", set)
        if not set:
            return {"error": "update requires a non-empty 'set' dict"}
        if not isinstance(where, dict):
            return _fmterr("where", where)
        if not where:
            # C_safety: refuse unrestricted updates
            return {"error": "SAFETY: update requires a non-empty 'where'"}
        err = self._check_cols(table, set) or self._check_cols(table, where)
        if err:
            return err
        w, wvals = _where_clause(where)
        sql = 'UPDATE "%s" SET %s WHERE %s' % (
            table,
            ", ".join('"%s" = ?' % k for k in set),
            w)
        vals = list(set.values()) + wvals
        cur = self._conn.execute(sql, vals)
        self._conn.commit()
        return {"ok": True, "updated": cur.rowcount}

    def delete(self, table, where):
        err = self._check_table(table)
        if err:
            return err
        if not isinstance(where, dict):
            return _fmterr("where", where)
        if not where:
            # C_safety: refuse unrestricted deletes
            return {"error": "SAFETY: delete requires a non-empty 'where'"}
        err = self._check_cols(table, where)
        if err:
            return err
        w, vals = _where_clause(where)
        sql = 'DELETE FROM "%s" WHERE %s' % (table, w)
        cur = self._conn.execute(sql, vals)
        self._conn.commit()
        return {"ok": True, "deleted": cur.rowcount}

    # -- dispatch ----------------------------------------------------------
    def call(self, tool, args):
        args = args or {}
        try:
            if tool == "list_tables":
                return self.list_tables()
            if tool == "read":
                return self.read(args.get("table"), args.get("filter"),
                                 args.get("limit", 50))
            if tool == "aggregate":
                return self.aggregate(args.get("table"), args.get("agg"),
                                      args.get("field"), args.get("filter"))
            if tool == "insert":
                return self.insert(args.get("table"), args.get("record"))
            if tool == "update":
                return self.update(args.get("table"), args.get("set"),
                                   args.get("where"))
            if tool == "delete":
                return self.delete(args.get("table"), args.get("where"))
            return {"error": "unknown tool %r" % (tool,)}
        except Exception as e:  # never crash an episode on a bad call
            return {"error": "%s: %s" % (type(e).__name__, e)}

    # -- predicate evaluation (evaluator-only) -----------------------------
    def eval_check(self, args):
        """Evaluate a CHECK pseudo-step predicate against the live DB.
        kinds: field_cmp, transfer_guard, agg_cmp, row_exists."""
        kind = args.get("kind")
        if kind == "field_cmp":
            r = self.read(args["table"], args.get("where"))
            if r.get("error") or r["n"] == 0:
                return False
            val = r["rows"][0].get(args["field"])
            if val is None:
                return False
            return _CMP[args["op"]](val, args["value"])
        if kind == "agg_cmp":
            a = self.aggregate(**args["agg_args"])
            if a.get("error"):
                return False
            return _CMP[args["op"]](a["value"], args["value"])
        if kind == "transfer_guard":
            # params: a {table,where,field}, min_a (source keeps >= min_a),
            #         b {table,where,field}, cap_b (dest has room >= amount),
            #         amount
            ra = self.read(args["a"]["table"], args["a"]["where"])
            rb = self.read(args["b"]["table"], args["b"]["where"])
            if ra.get("error") or rb.get("error") or ra["n"] == 0 or rb["n"] == 0:
                return False
            va = ra["rows"][0].get(args["a"]["field"])
            vb = rb["rows"][0].get(args["b"]["field"])
            if va is None or vb is None:
                return False
            return (va - args["amount"] >= args.get("min_a", 0)
                    and vb + args["amount"] <= args.get("cap_b", 10 ** 9))
        if kind == "row_exists":
            r = self.read(args["table"], args.get("where"))
            return bool(not r.get("error") and r["n"] > 0)
        raise ValueError("unknown check kind %r" % (kind,))

    def check_terminal(self):
        """Evaluate all terminal predicates; return (ok, detail list)."""
        detail = []
        ok_all = True
        for p in self._terminal:
            ok = self._eval_pred(p)
            detail.append({"predicate": p, "ok": ok})
            ok_all = ok_all and ok
        return ok_all, detail

    def _eval_pred(self, p):
        t = p["type"]
        if t == "field_cmp":
            r = self.read(p["table"], p.get("where"))
            if r.get("error") or r["n"] == 0:
                return False
            val = r["rows"][0].get(p["field"])
            if val is None:
                return False
            return _CMP[p["op"]](val, p["value"])
        if t == "exists":
            r = self.read(p["table"], p.get("where"))
            return bool(not r.get("error") and r["n"] > 0)
        if t == "not_exists":
            r = self.read(p["table"], p.get("where"))
            return bool(not r.get("error") and r["n"] == 0)
        if t == "row_count":
            r = self.read(p["table"], p.get("where"), limit=100000)
            return (not r.get("error")) and _CMP[p["op"]](r["n"], p["value"])
        if t == "agg_cmp":
            a = self.aggregate(p["table"], p["agg"], p.get("field"),
                               p.get("filter"))
            return (not a.get("error")) and _CMP[p["op"]](a["value"], p["value"])
        raise ValueError("unknown predicate type %r" % (t,))

    # -- internals ---------------------------------------------------------
    def _check_table(self, table):
        if table not in self._tables:
            return {"error": "unknown table %r; tables: %s"
                             % (table, sorted(self._tables))}
        return None

    def _check_cols(self, table, d):
        bad = [k for k in (d or {}) if k not in self._columns[table]]
        if bad:
            return {"error": "unknown column(s) %s in table %r; columns: %s"
                             % (bad, table, self._columns[table])}
        return None
