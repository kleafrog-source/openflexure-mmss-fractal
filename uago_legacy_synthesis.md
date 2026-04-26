# UAGO Legacy System Synthesis for Mistral Prompt Enhancement

## 1. Core Principle: Autonomous Mathematical Discovery

The legacy UAGO system was designed to autonomously discover the underlying mathematical principles of geometric structures in images. It did not recognize objects by name but instead sought to find the generative formulas that could reproduce the observed patterns.

**Key takeaway for Mistral:** The prompt should emphasize the generation of mathematical formulas (IFS, L-systems, etc.) rather than descriptive labels.

## 2. The 7-Phase Cycle

The legacy system followed a strict 7-phase cycle:

1.  **Structure Detection:** Identify the region of interest (ROI).
2.  **Invariant Extraction:** Measure fundamental properties like fractal dimension, symmetry, and repetition.
3.  **Hypothesis Generation:** Propose potential mathematical families (e.g., "IFS fractal," "periodic tiling").
4.  **Adaptive Measurement:** Perform targeted measurements based on the hypotheses (e.g., measure branch angles if an L-system is suspected).
5.  **Model Search:** Generate a specific mathematical formula with parameters.
6.  **Validation:** Test the generated model.
7.  **Context Transition:** Prepare for the next level of analysis.

**Key takeaway for Mistral:** The new system will combine these phases into a single prompt, but the logical flow should be preserved. The prompt will provide all the necessary information (invariants, measurements) upfront, and Mistral will be asked to generate the final model.

## 3. Key Invariants and Measurements

The legacy system relied on a set of core invariants:

*   **Dimensionality:** Fractal dimension (box-counting).
*   **Symmetry:** Rotational and other symmetries.
*   **Repetition:** How periodic the structure is.
*   **Connectivity:** How connected the different parts are.
*   **Scales:** Ratios of sizes of different parts.
*   **Branching Angles:** For tree-like structures.

**Key takeaway for Mistral:** The new prompt should include these invariants as the primary input for the formula generation process.

## 4. Successful Formula/Model Types

The legacy system was capable of identifying several types of mathematical models:

*   **Iterated Function Systems (IFS):** For self-similar fractals like the Sierpinski triangle.
*   **L-systems:** For branching structures like plants and trees.
*   **Periodic Tilings:** For repeating patterns.
*   **Logarithmic Spirals:** For spiral structures.
*   **Algebraic Curves and Dynamical Systems:** For other complex patterns.

**Key takeaway for Mistral:** The prompt should guide Mistral to generate formulas in these formats, as they have been successful in the past.

## 5. Example Mistral Prompts from Legacy System

The legacy system used prompts like these:

*   **Hypothesis Generation:** "Generate EXACTLY 3 prioritized hypotheses. Each: id (H1-H3), desc (concise math, e.g., 'Hierarchical self-similarity via IFS, dim≈{...}'), priority (0.5-1.0 based on fit)."
*   **Model Search:** "Infer structure class (fractal, tiling, dynamical, Lie group, etc.) from invariants {...}, hyp {...}, measures {...}. Select minimal from {...}. Derive LaTeX formula + params."

**Key takeaway for Mistral:** These legacy prompts provide a solid foundation for the new, more comprehensive prompt. The new prompt will be a synthesis of these, but in a single call.

By incorporating these findings into the new Mistral prompt, we can leverage the successful patterns and logic from the legacy UAGO system to enhance the performance and accuracy of the new MMSS-Alpha-Formula architecture.