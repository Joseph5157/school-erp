# Claude Code

Read and follow [AGENTS.md](AGENTS.md) and the workflow it links
([docs/engineering/README.md](docs/engineering/README.md)). This file does not replace or
relax any rule there.

The commands you will need (lint, system check, migration check, targeted tests, CSS guard
tests, route inventory, PR checks, guarded merge) are in
[docs/engineering/README.md](docs/engineering/README.md#commands). The ones used most:

- `ruff check .`
- `python manage.py test core.tests.test_<area> --parallel 4 --noinput` (local runs need
  `DJANGO_DEBUG=True`)
- `gh pr checks <N>` on the current head before any merge

Do not run the full test suite locally unless asked; CI runs it.
