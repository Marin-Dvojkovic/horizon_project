# Documentation

This directory holds a configuration to automatically build a LaTeX and HTML documentation of the project.
The most recent pre-built version can be found under [`docs.pdf`](docs.pdf).

## Setup

**1. Install [Doxygen](https://www.doxygen.nl/manual/install.html)**

**2. Build documentation**

In the project root, run:

```bash
doxygen docs/Doxyfile
```

This builds a LaTeX and HTML version under [docs/](docs/).

**3. Compile LaTeX documentation**

```bash
cd docs/latex/ && make
```

**4. Read docs**
Read docs at [index.html](html/index.html) and [refman.pdf](latex/refman.pdf).
