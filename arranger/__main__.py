"""`python -m arranger` - the built-in demonstration.

A package cannot be executed with `-m` on its own; Python looks for a
`__main__.py` inside it. This is that file, and it is three lines because the work
is in `arranger.main()` - the same function the `jazz-arranger` console script
calls, so there is one entry point rather than two that can disagree.

It also keeps `make demo` working, which is the reason it is here rather than in
the Makefile as an inline `-c "from arranger import main; main()"`: the demo
should be runnable the way a user would run it.
"""

from __future__ import annotations

from . import main

if __name__ == "__main__":
    main()
