# Compliance benchmark: quick_dinov2_variety

967 labelled areas (100 non-compliant), granularity `variety`. Points: +1 correct, -2 wrong.

## New photos, seen cameras (`images`)

| Engine | Method | Points | Correct | Caught | False alarms | Images all correct | Product id | Threshold(s) |
|---|---|---|---|---|---|---|---|---|
| dinov2 | always | 667 | 867/967 | 0/100 | 0 | 54/91 |  |  |
| dinov2 | classifier+gsd | 874 | 936/967 | 71/100 | 2 | 74/91 | 801/817 | 0.1 |

## Time (CPU)

| Engine | ms / camera image | ms / area | training (s) |
|---|---|---|---|
| dinov2 | 906 | 84.3 | 5.5 |
