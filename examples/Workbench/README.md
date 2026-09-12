# Workbench — A Meo Reference Module

Workbench is a general-purpose file and document working Module for A Meo.

It allows A Meo to work with files and documents in a controlled workspace, including reading, analyzing, creating, and modifying supported file types.

Workbench is already included with the standard A Meo installation.

The source published in this folder is provided as a **reference implementation for A Meo Module development**.

## Why is Workbench published here?

A Meo's Core implementation is private.

Third-party Modules do not need access to the Core source. They are developed against the:

**A Meo Public Module Contract V1.3**

Workbench is provided as a real, working example of a Module built for that public boundary.

Together:

- The **Public Module Contract** defines the boundary.
- **Workbench** shows a complete Module implementation.
- `build_project.py` demonstrates how the Module project can be generated from the published source.

This makes the folder useful for both developers and coding AI systems that want to understand how an A Meo Module is structured and built.

## Files

### `WorkbenchV1.1.txt`

The published Workbench Module source.

### `build_project.py`

A helper used to generate the Workbench Module project from the published source.

## Building the reference Module

You do **not** need to build Workbench in order to use A Meo.

Workbench is already included with A Meo.

The build files are provided for development, learning, experimentation, and as a reference when creating new Modules.

If you want to reproduce the reference Module, place:

- `WorkbenchV1.1.txt`
- `build_project.py`

in the A Meo Core folder and run:

```bash
python build_project.py

Building your own A Meo Module

A practical starting point is to give a coding AI:

Public_Module_Contract_v1.3.md
WorkbenchV1.1.txt
A description of the capability you want your Module to provide.

The Public Module Contract defines what a Module may rely on.

Workbench provides a real implementation to learn from.

Your Module should remain Plug & Play, path-independent, AI-independent, and OS-agnostic whenever its domain permits.

The Contract defines the boundary. Workbench shows how to build against it.
