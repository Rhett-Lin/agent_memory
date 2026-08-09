#!/usr/bin/env python
"""P-hat evaluator: learn P(program match | instruction, memory_text) on pilot/peval/pairs.jsonl.

Model: LogisticRegression (seed 42, class_weight='balanced') on
  - paired word TF-IDF features: elementwise product u*v and |u-v| of the L2-normalized
    tf-idf vectors of the instruction (u) and the memory text (v), shared vocabulary;
  - paired char_wb TF-IDF features, same construction;
  - dense "agreement" hand features: sim_tf / sim_embed, token jaccard + containment,
    number containment, comparator-polarity agreement (at or below / above / at least / ...),
    direction-word agreement (from/to/origin/target), action-verb containment, and
    archive/delete instr-only indicators (the benchmark's near-miss kinds flip exactly
    these program elements: flip_polarity, reverse_direction, wrong_child_set, skip_archive).

Label guardrail: input features come from instruction + memory text only, plus
sim_tf / sim_embed (computable from the texts at deployment). P/S labels are used
for training/evaluation only.

Evaluation (all deterministic, seed 42):
  - baseline reproduction on all 640 pairs: AUC(sim_tf), AUC(sim_embed), overall + S=1 subset
  - GroupKFold by family_idx (40 folds) out-of-fold AUC, overall + S=1
  - leave-one-archetype-out (4 folds) and leave-one-domain-out (4 folds) AUC
  - in-sample fit AUC, clearly labeled as an upper bound
  - per-scheme: P-hat AUC side-by-side with sim baselines on identical subsets

Writes:
  - pilot/peval/P_EVAL_RESULTS.json  (metrics)
  - pilot/peval/pair_scores.jsonl    (per-pair oof/full scores, consumed by gate_eval.py)
"""
import json
import pathlib
import re
import time

import numpy as np
import sklearn
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

HERE = pathlib.Path(__file__).resolve().parent
SEED = 42

TOKEN_RE = re.compile(r'[a-z][a-z_]+')
NUM_RE = re.compile(r'\d+')

# Comparator phrases -> polarity class. Extraction claims spans longest-phrase-first,
# so e.g. "at or below" wins over "below" at the same position.
CMP_WORD_PHRASES = [
    ('at or below', 'LE'), ('at most', 'LE'), ('no more than', 'LE'),
    ('not above', 'LE'), ('up to', 'LE'), ('does not exceed', 'LE'),
    ('at or above', 'GE'), ('at least', 'GE'), ('no fewer than', 'GE'),
    ('no less than', 'GE'), ('not below', 'GE'),
    ('greater than', 'GT'), ('more than', 'GT'), ('above', 'GT'),
    ('over', 'GT'), ('exceeds', 'GT'), ('exceed', 'GT'),
    ('less than', 'LT'), ('fewer than', 'LT'), ('below', 'LT'), ('under', 'LT'),
]
CMP_CLASSES = ('LE', 'LT', 'GE', 'GT')

VERB_LEXICON = {
    'archive', 'delete', 'transfer', 'escalate', 'move', 'copy', 'read', 'verify',
    'confirm', 'notify', 'send', 'insert', 'aggregate', 'count', 'update', 'remove',
    'schedule', 'cancel', 'sort', 'label', 'write', 'set', 'check', 'compare',
}
DIR_LEXICON = {'from', 'to', 'origin', 'target', 'source', 'destination',
               'warehouse', 'store', 'into', 'onto'}

HAND_NAMES = [
    'sim_tf', 'sim_embed',
    'tok_jaccard', 'tok_cont_i_in_m', 'tok_cont_m_in_i',
    'num_containment', 'num_jaccard',
    'cmp_present_i', 'cmp_containment', 'cmp_missing_in_m', 'cmp_conflict',
    'dir_containment', 'verb_containment',
    'archive_i_only', 'delete_i_only',
]


def comparator_classes(text: str) -> set:
    """Extract comparator polarity classes from text (longest match claims the span)."""
    low = text.lower()
    claimed = np.zeros(len(low) + 1, dtype=bool)
    found = set()
    for phrase, cls in sorted(CMP_WORD_PHRASES, key=lambda pc: -len(pc[0])):
        for m in re.finditer(r'\b' + re.escape(phrase) + r'\b', low):
            if claimed[m.start():m.end()].any():
                continue
            claimed[m.start():m.end()] = True
            found.add(cls)
    return found


def tokens(text: str) -> set:
    return set(TOKEN_RE.findall(text.lower()))


def numbers(text: str) -> set:
    return set(NUM_RE.findall(text))


def _containment(a: set, b: set) -> float:
    if not a:
        return 0.0
    return len(a & b) / len(a)


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def hand_features(instr: str, mem: str, sim_tf: float, sim_embed: float) -> list:
    ti, tm = tokens(instr), tokens(mem)
    ni, nm = numbers(instr), numbers(mem)
    ci, cm = comparator_classes(instr), comparator_classes(mem)
    di, dm = ti & DIR_LEXICON, tm & DIR_LEXICON
    vi, vm = ti & VERB_LEXICON, tm & VERB_LEXICON
    return [
        sim_tf, sim_embed,
        _jaccard(ti, tm), _containment(ti, tm), _containment(tm, ti),
        _containment(ni, nm), _jaccard(ni, nm),
        1.0 if ci else 0.0, _containment(ci, cm),
        1.0 if (ci and not cm) else 0.0,
        1.0 if (ci and not ci <= cm) else 0.0,
        _containment(di, dm), _containment(vi, vm),
        1.0 if ('archive' in ti and 'archive' not in tm) else 0.0,
        1.0 if ('delete' in ti and 'delete' not in tm) else 0.0,
    ]


_WS_RE = re.compile(r'\s+')


def _char_wb_ngrams(text, n_lo=3, n_hi=5):
    """Replicates sklearn's char_wb ngram extraction (word-boundary padded, lowercased)."""
    text = _WS_RE.sub(' ', text.lower())
    grams = []
    for tok in text.split(' '):
        if not tok:
            continue
        padded = f' {tok} '
        L = len(padded)
        for n in range(n_lo, n_hi + 1):
            grams.extend(padded[i:i + n] for i in range(L - n + 1))
    return grams


class PairFeaturizer:
    """Word + char TF-IDF pair features (product and |diff|), fit on training texts only.

    The char ngram list per unique text is memoized globally (CHAR_CACHE, label-free,
    pure function of the text), but char vocabulary and idf are refit inside every
    fold on training texts only -- same leakage guarantees as a fresh vectorizer.
    """

    def __init__(self, char_cache):
        self.char_cache = char_cache
        self.wv = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
        self.cv = TfidfVectorizer(analyzer=self.char_cache.__getitem__, min_df=3,
                                  max_features=4000, sublinear_tf=True)

    def fit(self, instrs, mems):
        self.wv.fit(list(instrs) + list(mems))
        self.cv.fit(list(instrs) + list(mems))
        return self

    @staticmethod
    def _pair_block(u, v):
        prod = u.multiply(v)
        diff = (u - v).tocsr()
        diff.data = np.abs(diff.data)  # |u-v| has the same sparsity pattern as u-v
        diff.eliminate_zeros()
        return sparse.hstack([prod, diff], format='csr')

    def transform(self, instrs, mems):
        w = self._pair_block(self.wv.transform(instrs), self.wv.transform(mems))
        c = self._pair_block(self.cv.transform(instrs), self.cv.transform(mems))
        return sparse.hstack([w, c], format='csr')


def build_matrix(train_idx, test_idx, instrs, mems, hand, char_cache):
    """Fold-safe featurization: TF-IDF and hand-feature scaler fit on train only."""
    feat = PairFeaturizer(char_cache).fit(
        [instrs[i] for i in train_idx], [mems[i] for i in train_idx])
    Xtr = feat.transform([instrs[i] for i in train_idx], [mems[i] for i in train_idx])
    Xte = feat.transform([instrs[i] for i in test_idx], [mems[i] for i in test_idx])
    scaler = StandardScaler().fit(hand[train_idx])
    Htr = sparse.csr_matrix(scaler.transform(hand[train_idx]))
    Hte = sparse.csr_matrix(scaler.transform(hand[test_idx]))
    return sparse.hstack([Xtr, Htr], format='csr'), sparse.hstack([Xte, Hte], format='csr')


def new_model():
    # liblinear converges orders of magnitude faster than lbfgs on this wide sparse
    # design at equal test ranking (verified: Spearman corr of oof scores = 1.0000 vs
    # lbfgs max_iter=3000 on a smoke fold); tol=1e-2 keeps the ~10 min runtime budget.
    return LogisticRegression(C=1.0, class_weight='balanced', solver='liblinear',
                              tol=1e-2, max_iter=500, random_state=SEED)


def oof_scores(splits, instrs, mems, hand, P, char_cache):
    scores = np.full(len(P), np.nan)
    for train_idx, test_idx in splits:
        Xtr, Xte = build_matrix(train_idx, test_idx, instrs, mems, hand, char_cache)
        model = new_model().fit(Xtr, P[train_idx])
        scores[test_idx] = model.predict_proba(Xte)[:, 1]
    assert not np.isnan(scores).any()
    return scores


def auc_pair(P, S, scores):
    out = {'overall': float(roc_auc_score(P, scores))}
    m = S == 1
    out['S1_subset'] = float(roc_auc_score(P[m], scores[m]))
    out['n'] = int(len(P))
    out['n_S1'] = int(m.sum())
    return out


def per_group_auc(P, S, scores, groups):
    per = {}
    for g in sorted(set(groups)):
        m = np.array([gg == g for gg in groups])
        per[str(g)] = auc_pair(P[m], S[m], scores[m])
    return per


def main() -> None:
    t0 = time.time()
    pairs = [json.loads(l) for l in open(HERE / 'pairs.jsonl')]
    assert len(pairs) == 640
    instrs = [p['instruction'] for p in pairs]
    mems = [p['memory_text'] for p in pairs]
    P = np.array([p['P'] for p in pairs])
    S = np.array([p['S'] for p in pairs])
    fam = np.array([p['family_idx'] for p in pairs])
    arch = np.array([p['archetype'] for p in pairs])
    dom = np.array([p['domain'] for p in pairs])
    sim_tf = np.array([p['sim_tf'] for p in pairs])
    sim_emb = np.array([p['sim_embed'] for p in pairs])
    hand = np.array([hand_features(p['instruction'], p['memory_text'],
                                   p['sim_tf'], p['sim_embed']) for p in pairs])

    # one-time char ngram memoization over the unique texts in this dataset
    char_cache = {t: _char_wb_ngrams(t) for t in set(instrs) | set(mems)}

    results = {
        'config': {
            'seed': SEED, 'sklearn_version': sklearn.__version__,
            'model': 'LogisticRegression(C=1.0, class_weight=balanced, solver=liblinear, tol=1e-2, max_iter=500)',
            'sparse_features': 'word(1-2,min_df=2)+char_wb(3-5,min_df=3,max_features=4000) tf-idf, pair=(u*v,|u-v|)',
            'hand_features': HAND_NAMES,
            'leakage_control': 'TF-IDF vocabularies and hand-feature scaler refit inside every fold',
        },
        'dataset': {
            'n_pairs': len(pairs), 'n_P1': int(P.sum()), 'n_S1': int(S.sum()),
            'n_families': len(set(fam)), 'n_archetypes': len(set(arch)),
            'n_domains': len(set(dom)),
        },
        'schemes': {},
    }

    # --- baseline reproduction on all 640 pairs ---
    results['baseline_reproduction'] = {
        'sim_tf': auc_pair(P, S, sim_tf),
        'sim_embed': auc_pair(P, S, sim_emb),
    }

    all_idx = np.arange(len(P))

    # --- in-sample (upper bound, labeled as such) ---
    Xtr, Xte = build_matrix(all_idx, all_idx, instrs, mems, hand, char_cache)
    full_model = new_model().fit(Xtr, P)
    phat_full = full_model.predict_proba(Xte)[:, 1]
    results['schemes']['insample_upper_bound'] = {
        'note': 'resubstitution fit on all 640 pairs; optimistically biased, upper bound only',
        'phat': auc_pair(P, S, phat_full),
        'sim_tf': results['baseline_reproduction']['sim_tf'],
        'sim_embed': results['baseline_reproduction']['sim_embed'],
    }

    # --- GroupKFold by family (40 folds) ---
    splits = list(GroupKFold(n_splits=40).split(all_idx, P, fam))
    phat_oof_fam = oof_scores(splits, instrs, mems, hand, P, char_cache)
    results['schemes']['groupkfold_family_40'] = {
        'phat': auc_pair(P, S, phat_oof_fam),
        'sim_tf': results['baseline_reproduction']['sim_tf'],
        'sim_embed': results['baseline_reproduction']['sim_embed'],
    }

    # --- leave-one-archetype-out ---
    splits = list(LeaveOneGroupOut().split(all_idx, P, arch))
    phat_oof_arch = oof_scores(splits, instrs, mems, hand, P, char_cache)
    results['schemes']['leave_one_archetype_out'] = {
        'phat': auc_pair(P, S, phat_oof_arch),
        'sim_tf': results['baseline_reproduction']['sim_tf'],
        'sim_embed': results['baseline_reproduction']['sim_embed'],
        'per_held_out_archetype': per_group_auc(P, S, phat_oof_arch, arch),
    }

    # --- leave-one-domain-out ---
    splits = list(LeaveOneGroupOut().split(all_idx, P, dom))
    phat_oof_dom = oof_scores(splits, instrs, mems, hand, P, char_cache)
    results['schemes']['leave_one_domain_out'] = {
        'phat': auc_pair(P, S, phat_oof_dom),
        'sim_tf': results['baseline_reproduction']['sim_tf'],
        'sim_embed': results['baseline_reproduction']['sim_embed'],
        'per_held_out_domain': per_group_auc(P, S, phat_oof_dom, dom),
    }

    # --- hand-feature weights of the full model (introspection only) ---
    k = len(HAND_NAMES)
    coefs = full_model.coef_[0][-k:]
    results['hand_feature_weights_full_fit'] = dict(
        sorted(zip(HAND_NAMES, [float(c) for c in coefs]), key=lambda kv: -abs(kv[1])))

    results['runtime_seconds'] = round(time.time() - t0, 2)
    with open(HERE / 'P_EVAL_RESULTS.json', 'w') as f:
        json.dump(results, f, indent=1)

    # --- per-pair scores for gate_eval.py ---
    with open(HERE / 'pair_scores.jsonl', 'w') as f:
        for i, p in enumerate(pairs):
            f.write(json.dumps({
                'memory_id': p['memory_id'], 'family_idx': p['family_idx'],
                'target_sibling': p['target_sibling'], 'cell': p['cell'],
                'P': p['P'], 'S': p['S'],
                'sim_tf': p['sim_tf'], 'sim_embed': p['sim_embed'],
                'phat_oof_family': float(phat_oof_fam[i]),
                'phat_oof_archetype': float(phat_oof_arch[i]),
                'phat_oof_domain': float(phat_oof_dom[i]),
                'phat_full': float(phat_full[i]),
            }) + '\n')

    # --- stdout summary ---
    def row(name, d):
        return (f"{name:<28} P-hat {d['phat']['overall']:.3f} / S=1 {d['phat']['S1_subset']:.3f}"
                f"   sim_tf {d['sim_tf']['overall']:.3f} / {d['sim_tf']['S1_subset']:.3f}"
                f"   sim_embed {d['sim_embed']['overall']:.3f} / {d['sim_embed']['S1_subset']:.3f}")
    print('scheme                        P-hat overall/S=1       sim_tf overall/S=1    sim_embed overall/S=1')
    for name in ['insample_upper_bound', 'groupkfold_family_40',
                 'leave_one_archetype_out', 'leave_one_domain_out']:
        print(row(name, results['schemes'][name]))
    print(f"\nruntime: {results['runtime_seconds']}s -> P_EVAL_RESULTS.json, pair_scores.jsonl")


if __name__ == '__main__':
    main()
