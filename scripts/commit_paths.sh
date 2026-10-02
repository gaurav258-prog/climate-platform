#!/usr/bin/env bash
# Commit exactly the named paths, whatever else is staged in the shared checkout (E28: two sessions share one index).
#
#   scripts/commit_paths.sh "message" path [path ...]
#
# Builds the commit in a private index (HEAD + the named paths), moves the checked-out branch to it, then updates only those entries in
# the shared index. Refuses (E39): no paths; a path with no change against HEAD; a tree identical to HEAD's.
# Pushing is left to the caller.
set -euo pipefail

msg="${1:?usage: commit_paths.sh \"message\" path [path ...]}"
shift
[ "$#" -gt 0 ] || { echo "commit_paths: no paths named" >&2; exit 2; }

cd "$(git rev-parse --show-toplevel)"
# the branch checked out HERE moves — never a fixed name (from a worktree, a fixed 'main' moved another checkout's branch)
branch="$(git symbolic-ref -q HEAD)" || { echo "commit_paths: HEAD is detached — check out a branch" >&2; exit 2; }
for p in "$@"; do
  if [ -e "$p" ]; then
    if git cat-file -e "HEAD:$p" 2>/dev/null && git diff --quiet HEAD -- "$p"; then
      echo "commit_paths: $p has no change against HEAD" >&2; exit 2
    fi
  elif ! git cat-file -e "HEAD:$p" 2>/dev/null; then
    echo "commit_paths: $p neither exists nor is tracked" >&2; exit 2
  fi
done

idx="$(mktemp "${TMPDIR:-/tmp}/commit_paths.XXXXXX")"
trap 'rm -f "$idx"' EXIT
export GIT_INDEX_FILE="$idx"
git read-tree HEAD
git update-index --add --remove -- "$@"
tree="$(git write-tree)"
if [ "$tree" = "$(git rev-parse 'HEAD^{tree}')" ]; then
  echo "commit_paths: nothing to commit — the tree equals HEAD's" >&2; exit 2
fi
commit="$(git commit-tree "$tree" -p HEAD -m "$msg")"
git update-ref "$branch" "$commit" HEAD
unset GIT_INDEX_FILE

for p in "$@"; do          # the shared index follows the commit for these paths only
  if git cat-file -e "HEAD:$p" 2>/dev/null; then
    git update-index --add --cacheinfo "$(git ls-tree HEAD -- "$p" | awk '{print $1}'),$(git rev-parse "HEAD:$p"),$p"
  else
    git update-index --force-remove -- "$p"
  fi
done
git log --oneline -1
git show --stat --format= HEAD | tail -1
