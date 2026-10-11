# Compliance benchmark: phase2

967 labelled areas (100 non-compliant), granularity `category`. Points: +1 correct, -2 wrong.

## New photos, seen cameras (`images`)

| Engine | Method | Points | Correct | Caught | False alarms | Images all correct | Product id | Threshold(s) |
|---|---|---|---|---|---|---|---|---|
| clip | always | 667 | 867/967 | 0/100 | 0 | 54/91 |  |  |
| clip | area_cosine_0.65 | 769 | 901/967 | 46/100 | 12 | 55/91 |  | 0.65 |
| clip | area_cosine | 778 | 904/967 | 65/100 | 28 | 53/91 |  | 0.65,0.75 |
| clip | classifier | 811 | 915/967 | 52/100 | 4 | 64/91 | 806/817 | 0.15,0.3,0.5 |
| clip | gsd_only | 445 | 793/967 | 27/100 | 101 | 23/91 | 361/817 | 0.01 |
| clip | classifier+gsd | 805 | 913/967 | 47/100 | 1 | 65/91 | 798/817 | 0.01,0.02 |
| clip | text | 787 | 907/967 | 40/100 | 0 | 66/91 |  | 0.03 |
| dinov2 | always | 667 | 867/967 | 0/100 | 0 | 54/91 |  |  |
| dinov2 | area_cosine_0.65 | 796 | 910/967 | 79/100 | 36 | 53/91 |  | 0.65 |
| dinov2 | area_cosine | 817 | 917/967 | 79/100 | 29 | 60/91 |  | 0.55,0.6 |
| dinov2 | classifier | 835 | 923/967 | 60/100 | 4 | 65/91 | 808/817 | 0.1,0.2,0.3 |
| dinov2 | gsd_only | 541 | 825/967 | 23/100 | 65 | 36/91 | 443/817 | 0.01,0.02 |
| dinov2 | classifier+gsd | 829 | 921/967 | 59/100 | 5 | 64/91 | 806/817 | 0.05,0.1,0.2,0.3 |

## Unseen cameras (`cameras`)

| Engine | Method | Points | Correct | Caught | False alarms | Images all correct | Product id | Threshold(s) |
|---|---|---|---|---|---|---|---|---|
| clip | always | 667 | 867/967 | 0/100 | 0 | 54/91 |  |  |
| clip | area_cosine_0.65 | 667 | 867/967 | 0/100 | 0 | 54/91 |  | 0.65 |
| clip | area_cosine | 667 | 867/967 | 0/100 | 0 | 54/91 |  | 0.65,0.75,0.8 |
| clip | classifier | 679 | 871/967 | 13/100 | 9 | 53/91 | 196/817 | 0.01,0.02,0.05,0.1 |
| clip | gsd_only | 445 | 793/967 | 27/100 | 101 | 23/91 | 361/817 | 0.01 |
| clip | classifier+gsd | 472 | 802/967 | 24/100 | 89 | 27/91 | 385/817 | 0.01 |
| clip | text | 748 | 894/967 | 27/100 | 0 | 66/91 |  | 0.02,0.03 |
| dinov2 | always | 667 | 867/967 | 0/100 | 0 | 54/91 |  |  |
| dinov2 | area_cosine_0.65 | 667 | 867/967 | 0/100 | 0 | 54/91 |  | 0.65 |
| dinov2 | area_cosine | 667 | 867/967 | 0/100 | 0 | 54/91 |  | 0.35,0.55 |
| dinov2 | classifier | 721 | 885/967 | 24/100 | 6 | 61/91 | 217/817 | 0.01,0.05 |
| dinov2 | gsd_only | 538 | 824/967 | 22/100 | 65 | 36/91 | 443/817 | 0.01,0.02 |
| dinov2 | classifier+gsd | 601 | 845/967 | 22/100 | 44 | 42/91 | 477/817 | 0.01,0.02 |

## Time (CPU)

| Engine | ms / camera image | ms / area | training (s) |
|---|---|---|---|
| clip | 682 | 63.5 | 3.1 |
| dinov2 | 860 | 80.0 | 4.4 |
