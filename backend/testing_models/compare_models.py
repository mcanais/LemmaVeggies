import numpy as np
from sklearn.model_selection import StratifiedKFold
from eval_utils import load_human_dataset, compute_competition_score

import approach1_dinov2 as m1
import approach2_multitask as m2
import approach3_supcon as m3
import approach4_clip_improved as m4


def run_benchmark():
    records = load_human_dataset()
    print(f"Loaded {len(records)} verified crop annotations from human.jsonl.")

    strat_keys = [f"{r['compliant']}_{r['stock_value']}" for r in records]
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # Pre-extract cached embeddings for models 1, 3, and 4
    print("Extracting DINOv2 features for Approaches 1 & 3...")
    paths = [r["path"] for r in records]
    X_dino_b = m1.extract_features(paths)
    X_dino_s = m3.extract_base_feats(records)

    print("Extracting CLIP features for Approach 4...")
    clip_pipe = m4.Approach4CLIPPipeline()
    X_clip_img, X_clip_comb = clip_pipe.extract_features_and_text_scores(records)

    scores = {
        "Approach 1 (DINOv2 + MLP)": [],
        "Approach 2 (Multi-Task ConvNeXt)": [],
        "Approach 3 (Supervised Metric/SupCon)": [],
        "Approach 4 (CLIP Alignment Probing)": []
    }

    for fold, (train_idx, val_idx) in enumerate(skf.split(records, strat_keys), 1):
        print(f"\n--- Running Fold {fold}/5 ---")
        train_recs = [records[i] for i in train_idx]
        val_recs = [records[i] for i in val_idx]

        y_comp_train = [r["compliant"] for r in train_recs]
        y_stock_train = [r["stock_value"] for r in train_recs]
        y_comp_val = [r["compliant"] for r in val_recs]
        y_stock_val = [r["stock_value"] for r in val_recs]

        # 1. Benchmark Approach 1
        a1 = m1.Approach1DINOv2Pipeline()
        a1.fit(X_dino_b[train_idx], y_comp_train, y_stock_train)
        p_c1, p_s1 = a1.predict(X_dino_b[val_idx])
        sc1 = compute_competition_score(y_comp_val, p_c1, y_stock_val, p_s1)
        scores["Approach 1 (DINOv2 + MLP)"].append(sc1["total_score"])

        # 2. Benchmark Approach 2 (Train for 4 epochs per fold to speed up)
        p_c2, p_s2 = m2.train_multitask(train_recs, val_recs, epochs=4)
        sc2 = compute_competition_score(y_comp_val, p_c2, y_stock_val, p_s2)
        scores["Approach 2 (Multi-Task ConvNeXt)"].append(sc2["total_score"])

        # 3. Benchmark Approach 3
        a3 = m3.Approach3MetricPipeline()
        a3.fit(X_dino_s[train_idx], train_recs, epochs=15)
        p_c3, p_s3 = a3.predict(X_dino_s[val_idx], val_recs)
        sc3 = compute_competition_score(y_comp_val, p_c3, y_stock_val, p_s3)
        scores["Approach 3 (Supervised Metric/SupCon)"].append(sc3["total_score"])

        # 4. Benchmark Approach 4
        a4 = m4.Approach4CLIPPipeline()
        a4.fit(X_clip_img[train_idx], X_clip_comb[train_idx], y_comp_train, y_stock_train)
        p_c4, p_s4 = a4.predict(X_clip_img[val_idx], X_clip_comb[val_idx])
        sc4 = compute_competition_score(y_comp_val, p_c4, y_stock_val, p_s4)
        scores["Approach 4 (CLIP Alignment Probing)"].append(sc4["total_score"])

    print("\n" + "=" * 55)
    print("FINAL BENCHMARK RESULTS (Average Competition Points)")
    print("=" * 55)
    best_name = None
    best_mean = -float("inf")

    for model_name, fold_scores in scores.items():
        avg = np.mean(fold_scores)
        std = np.std(fold_scores)
        print(f"{model_name:38s}: {avg:6.1f} ± {std:4.1f} pts")
        if avg > best_mean:
            best_mean = avg
            best_name = model_name

    print("-" * 55)
    print(f"Top Performer: {best_name} ({best_mean:.1f} pts)")
    print("=" * 55)


if __name__ == "__main__":
    run_benchmark()
