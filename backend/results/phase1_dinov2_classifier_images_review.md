# Review: `dinov2:classifier:images` (phase1)

| Camera | Labelled | Correct | Wrong products caught | Missed | False alarms |
|---|---|---|---|---|---|
| 6215 | 120 | 120 | 24 | 0 | 0 |
| 6371 | 117 | 117 | 0 | 0 | 0 |
| 6373 | 118 | 101 | 0 | 16 | 1 |
| 6376 | 207 | 195 | 36 | 12 | 0 |
| 6383 | 117 | 107 | 0 | 9 | 1 |
| 6385 | 27 | 27 | 0 | 0 | 0 |
| 6386 | 18 | 17 | 0 | 0 | 1 |
| 6443 | 39 | 36 | 0 | 3 | 0 |
| 6462 | 27 | 27 | 0 | 0 | 0 |
| 6468 | 48 | 48 | 0 | 0 | 0 |
| 6491 | 30 | 29 | 0 | 0 | 1 |
| 6591 | 30 | 30 | 0 | 0 | 0 |
| 6594 | 39 | 39 | 0 | 0 | 0 |
| 6781 | 30 | 30 | 0 | 0 | 0 |
| **all** | 967 | 923 | 60 | 40 | 4 |

## Missed wrong products: 40

![Missed wrong products](phase1_dinov2_classifier_images_missed.jpg)

6373_1 ×13, 6376_4 ×5, 6376_5 ×4, 6373_2 ×3, 6376_3 ×3, 6443_3 ×3, 6383_1 ×1, 6383_2 ×1, 6383_3 ×1, 6383_4 ×1, 6383_5 ×1, 6383_6 ×1, 6383_7 ×1, 6383_8 ×1, 6383_9 ×1

## False alarms: 4

![False alarms](phase1_dinov2_classifier_images_false_alarms.jpg)

6373_5 ×1, 6383_7 ×1, 6386_1 ×1, 6491_5 ×1

## Flagged on unlabelled areas (final model): 41

![Flagged on unlabelled areas (final model)](phase1_dinov2_classifier_images_unlabelled_flags.jpg)

6594_2 ×4, 6594_3 ×4, 6594_12 ×4, 6594_13 ×4, 6443_5 ×3, 6468_7 ×3, 6468_8 ×3, 6468_11 ×3, 6468_12 ×3, 6468_14 ×3, 6594_9 ×3, 6443_3 ×2, 6468_13 ×1, 6591_5 ×1
