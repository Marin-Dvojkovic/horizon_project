# Documentation

## Setup

**1. Install [Doxygen](https://www.doxygen.nl/manual/install.html)**

**2. Build documentation**

In the project root, run:

```bash
doxygen docs/Doxyfile
```

This builds a latex and html version under [docs/](docs/).

**3. Compile Latex documentation**

```bash
cd docs/latex/ && make
```

**4. Read docs**
Read docs at [index.html](html/index.html) and [refman.pdf](latex/refman.pdf).
