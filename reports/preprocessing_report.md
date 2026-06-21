# Spectral Database Preprocessing Report

Generated: 2026-06-16T13:20:01.556176

## Dataset Summary

- **Total spectra processed**: 1850
- **Total spectra accepted**: 1803
- **Total spectra rejected**: 47
- **Acceptance rate**: 97.5%

## Mineral Statistics

| Mineral | Count |
|---------|-------|
| Albite | 100 |
| Andradite | 100 |
| Augite | 100 |
| Dolomite | 100 |
| Grossular | 100 |
| Hypersthene | 100 |
| Microcline | 100 |
| Muscovite | 100 |
| Olivine | 100 |
| Quartz | 100 |
| Calcite | 99 |
| Enstatite | 98 |
| Rutile | 95 |
| Spinel | 95 |
| Diopside | 93 |
| Beryl | 92 |
| Orthoclase | 89 |
| Zircon | 68 |
| Apatite | 58 |
| Pyrope | 16 |

## Source Library Statistics

| Library | Count |
|---------|-------|
| relab | 1001 |
| usgs | 614 |
| rruff | 188 |

## Wavelength Statistics

- **Minimum wavelength**: 400.0 nm
- **Maximum wavelength**: 2500.0 nm
- **Mean coverage**: 100.0%
- **Wavelength range**: 2100.0 nm

## Spectral Integrity Metrics

- **Average coverage per mineral**: 100.0%
- **Total negatives clipped**: 8243
- **Total outlier adjustments**: 324220
- **Average pre/post variance ratio**: 0.9905365331998626

## Cleaning Statistics

- **NaNs removed**: 0
- **Duplicates removed**: 277
- **Outlier adjustments**: 324220
- **Negatives clipped**: 8243
- **Spectra rejected (cleaning)**: 47
- **Significantly altered spectra**: 1418

### Per-Library Cleaning Intensity

| Library | Processed | NaNs Removed | Duplicates Removed | Outliers Adjusted | Negatives Clipped |
|---------|-----------|-------------|-------------------|-------------------|-------------------|
| RELAB | 1017 | 0 | 277 | 271273 | 339 |
| RRUFF | 188 | 0 | 0 | 12420 | 13 |
| USGS | 637 | 0 | 0 | 40527 | 7891 |

## Spectral Distortion Analysis

### Spectral Angle Mapper (SAM) Distribution

- **Mean SAM angle**: 0.9483 radians
- **Median SAM angle**: 1.1974 radians
- **Min SAM angle**: 0.0010 radians
- **Max SAM angle**: 1.9845 radians
- **Std SAM angle**: 0.5912 radians

### Cosine Similarity Distribution

- **Mean cosine similarity**: 0.4799
- **Median cosine similarity**: 0.3648
- **Min cosine similarity**: -0.4020
- **Max cosine similarity**: 1.0000

### Combined Distortion Score Distribution

- **Mean distortion score**: 0.4312
- **Median distortion score**: 0.4485
- **Min distortion score**: 0.0003
- **Max distortion score**: 1.0000
- **Spectra with distortion > 0.15**: 1345

### Variance Preservation Ratio Distribution

- **Mean variance ratio**: 0.6737
- **Median variance ratio**: 0.7562
- **Min variance ratio**: 0.0000
- **Max variance ratio**: 1.0001
- **Over-smoothed (ratio < 0.5)**: 344
- **Over-amplified (ratio > 2.0)**: 0

### Per-Library Distortion Analysis

**RELAB**:
- Mean SAM angle: 1.4206 radians
- Mean distortion score: 0.6031

**RRUFF**:
- Mean SAM angle: 0.0376 radians
- Mean distortion score: 0.0136

**USGS**:
- Mean SAM angle: 0.6127 radians
- Mean distortion score: 0.3355

## Processing Parameters

### Smoothing
- Window length: 11
- Polynomial order: 3

### Interpolation
- Method: linear
- Wavelength range: 400-2500 nm
- Step size: 1 nm

### Normalization
- Method: minmax

## Quality Control Parameters

- Max missing fraction: 20.0%
- Outlier threshold: 3.0 σ
- Minimum spectrum points: 50

## Error Log Summary

Total issues reported: 8

### Recent Issues
- data\raw\USGS\Beryl\errorbars_for_S07LSAT8_Beryl_GDS9_lt150um_gs_BECKb_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Beryl\errorbars_for_S07LSAT8_Beryl_HS180.3B_BECKa_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Orthoclase\errorbars_for_S07LSAT8_Adularia_GDS57_Orthoclase_BECKb_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Orthoclase\errorbars_for_S07LSAT8_Orthoclase_NMNH113188_BECKb_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Orthoclase\errorbars_for_S07LSAT8_Orthoclase_NMNH142137_Fe_BECKb_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Rutile\errorbars_for_S07LSAT8_Rutile_HS126.3B_BECKc_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Zircon\errorbars_for_S07LSAT8_Zircon_WS522_BECKa_AREF.txt: parse_error: Insufficient points: 8
- data\raw\USGS\Zircon\S07LSAT8_Zircon_WS522_BECKa_AREF.txt: parse_error: Insufficient points: 8

## Rejection Diagnostics

- Total rejections: 47

### Rejections by Stage
- cleaning: 39
- parsing: 8

### Rejections by Library
- usgs: 31
- relab: 16

### Top Failure Reasons
- cleaning_failed: ['Insufficient valid points: 10 < 50']: 8
- parse_error: Insufficient points: 8: 8
- cleaning_failed: ['Insufficient valid points: 14 < 50']: 8
- cleaning_failed: ['Insufficient valid points: 17 < 50']: 7
- cleaning_failed: ['Length mismatch: wavelengths=236, reflectance=235']: 5
- cleaning_failed: ['Length mismatch: wavelengths=464, reflectance=463']: 2
- cleaning_failed: ['Length mismatch: wavelengths=235, reflectance=234']: 2
- cleaning_failed: ['Length mismatch: wavelengths=3529, reflectance=3528']: 1
- cleaning_failed: ['Length mismatch: wavelengths=454, reflectance=453']: 1
- cleaning_failed: ['Length mismatch: wavelengths=204, reflectance=203']: 1

### Acceptance Rates

#### Acceptance rate per mineral
- Albite: 100/100 (100.0%)
- Andradite: 100/100 (100.0%)
- Apatite: 58/58 (100.0%)
- Augite: 100/100 (100.0%)
- Beryl: 92/100 (92.0%)
- Calcite: 99/100 (99.0%)
- Diopside: 93/100 (93.0%)
- Dolomite: 100/100 (100.0%)
- Enstatite: 98/100 (98.0%)
- Grossular: 100/100 (100.0%)
- Hypersthene: 100/100 (100.0%)
- Microcline: 100/100 (100.0%)
- Muscovite: 100/100 (100.0%)
- Olivine: 100/100 (100.0%)
- Orthoclase: 89/100 (89.0%)
- Pyrope: 16/16 (100.0%)
- Quartz: 100/100 (100.0%)
- Rutile: 95/100 (95.0%)
- Spinel: 95/100 (95.0%)
- Zircon: 68/76 (89.5%)

#### Acceptance rate per library
- relab: 1001/1017 (98.4%)
- rruff: 188/188 (100.0%)
- usgs: 614/645 (95.2%)

---

*Generated by Spectral Database Preprocessing Pipeline*