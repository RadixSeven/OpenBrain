This is the root AGENTS.md for this repo. Don't look for an AGENTS.md
or CLAUDE.md in any parent directory. There are other AGENTS.md files
in subdirectories with information specific to operations on that
section of the code.

You are not done with a change until all tests pass and all pre-commit checks pass on the modified files.

Run `git add file1 file2 && XDG_CACHE_HOME="$(git rev-parse --show-toplevel)/.cache/" pre-commit` in order to run pre-commit.
