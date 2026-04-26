# Biological Fractal Definitions

This project now includes a first-pass biological and organic morphology layer on top of the existing fractal classifier.

## Current biological classes

### Fern-like leaflet / venation

- Target morphology: repeated plant-like branchlets, vein trees, pinnate leaflet structures
- Main cues: medium fractal dimension, moderate branching angle, elongated aspect ratio, some repetition, relatively smooth curvature

### Vascular / root-like branching network

- Target morphology: vessel trees, root arborization, simple organic branching tissue
- Main cues: branching geometry with moderate junction density and clear terminal endpoints

### Coral-like branching colony

- Target morphology: coral fragments, branching colony growth, irregular organic dendrites
- Main cues: stronger curvature, irregular branch tips, medium-to-high endpoint density

### Radial biological microform

- Target morphology: pollen-like grains, radiolarian-like shells, starburst microforms, simple radial bio-objects
- Main cues: radial symmetry classes such as `C5`, `C6`, `C8`, `C10`, `C12`, with curved or repeating spokes

### Mycelium / biofilm filament network

- Target morphology: fungal hyphae, mycelial mats, filamentous biofilm networks, reticulated tissue mesh
- Main cues: high branching, diffuse network density, curved filament paths, mesh-like connectivity

## Invariants used

The first-pass biological layer uses the existing invariant pipeline:

- `dimensionality`
- `symmetry_approx`
- `branching_angle`
- `mean_curvature`
- `aspect_ratio`
- `repetition_score`

It also derives simple network cues from the skeleton:

- junction density
- endpoint density
- line density

## Design intent

These classes are intentionally broad and conservative. They are not species identifiers and not pathology classifiers.

The goal is:

1. Start with geometry-aware morphological grouping
2. Surface plausible organic interpretations in reports
3. Combine them later with raw Mistral vision analysis and additional microscopy metadata

## Next extension ideas

- Add bilateral symmetry detection for leaves and segmented organisms
- Add lacunarity and gap statistics for porous tissues and colonies
- Add contour roughness for shells, spores, and crystalline-organic hybrids
- Add temporal comparison across captures to distinguish growth from static debris
- Add stain-aware or illumination-aware cues if imaging conditions become available
