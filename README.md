# MMSS-Alpha-Formula (v2.0)

## Adaptive Meta-Formula Synthesis (OpenFlexure + Mistral) with Safety Protocol

This project implements a bi-directional, iterative control loop (**Capture ⇌ MMSS ⇌ Mistral**) to automatically derive unique chemical/structural Meta-Formulas of micro-objects. It features a switchable safety flag to bypass microscope control commands during testing.

## Architecture

The system is designed around an iterative control loop orchestrated by the `MMSS_Engine`. The loop consists of the following steps:

1.  **Capture & Atomization:** An image is captured from the OpenFlexure microscope (or a mock API for testing), and the MMSS core performs "atomization" to extract key mathematical and semantic invariants.
2.  **Hypothesis Generation:** The extracted "atoms" are sent to the Mistral API, which generates a candidate Meta-Formula and a refinement command for the microscope.
3.  **Safety & Validation:** The refinement command is validated against a strict set of MMSS metrics. If the `MMSS_SAFETY_MODE_ACTIVE` flag is set, the command is simulated and skipped.
4.  **Execution & Iteration:** If the command is valid and the safety flag is not set, the command is executed on the microscope, and the loop repeats.
5.  **Termination:** The loop terminates when the Semantic Value (V) of the analysis reaches a predefined threshold or when the value of V stabilizes over multiple iterations.

## Usage

### Installation

```bash
pip install -r requirements.txt
```

### Setting up the Mistral API Key

To use the Mistral API for hypothesis generation, you need to provide an API key. Create a file named `.env` in the root of the project and add your API key like this:

```
MISTRAL_API_KEY="your_actual_api_key_here"
```

If the `MISTRAL_API_KEY` is not found, the system will fall back to a simulated response.

### Running the System

To run the system, you need to provide a path to an initial image.

```bash
python main.py <path_to_image>
```

### Safety Flag

The `MMSS_SAFETY_MODE_ACTIVE` environment variable controls the interaction with the microscope hardware.

*   **Safety Mode (for testing and simulation):**

```bash
MMSS_SAFETY_MODE_ACTIVE=True python main.py <path_to_image>
```

*   **Live Mode (for real hardware interaction):**

```bash
MMSS_SAFETY_MODE_ACTIVE=False python main.py <path_to_image>
```

## Deliverables

*   **UML Diagram:** A PlantUML diagram of the control loop can be found in `docs/uml.md`.
*   **Mistral Prompt:** The Jinja2 template for the Mistral prompt is located at `src/mmss/mistral_prompt.jinja2`.
*   **MMSS-Blockly JSON:** The completed MMSS-Blockly workflow is available in `MMSS-Blockly.json`.
