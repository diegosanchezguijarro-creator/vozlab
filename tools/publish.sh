#!/usr/bin/env bash
# VozLab — publish this repository to GitHub and cut the first release.
#
#   1) authenticate once:   gh auth login --hostname github.com --git-protocol https --web
#   2) publish:             bash tools/publish.sh
#
# The script pushes main, creates the vX.Y.Z tag matching client/vozlab/__init__.py,
# and lets GitHub Actions build the Windows installer.
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"
REPO_NAME="${REPO_NAME:-vozlab}"
VISIBILITY="--public"
[[ "${1:-}" == "--private" ]] && VISIBILITY="--private"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- checks ----
command -v gh >/dev/null 2>&1 || die "gh (GitHub CLI) not found. Install it or add ~/.local/bin to PATH."
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "$REPO_ROOT is not a git repository."

if ! gh auth status >/dev/null 2>&1; then
  cat <<'EOF'
Not authenticated with GitHub yet. Run this first:

    gh auth login --hostname github.com --git-protocol https --web

It prints a one-time code; open https://github.com/login/device in the browser
on your laptop, paste the code, and approve. Then run this script again.
EOF
  exit 1
fi

GH_USER="$(gh api user --jq .login)"
GH_ID="$(gh api user --jq .id)"
say "Authenticated as $GH_USER"

# ------------------------------------------------------- commit identity ----
current_name="$(git config user.name || true)"
current_email="$(git config user.email || true)"
if [[ "$current_name" == "VozLab" || -z "$current_name" ]]; then
  say "Setting git identity to your GitHub account"
  git config user.name "$GH_USER"
  git config user.email "${GH_ID}+${GH_USER}@users.noreply.github.com"
  if ! git remote get-url origin >/dev/null 2>&1; then
    # nothing pushed yet: re-author every commit as the real user
    GIT_SEQUENCE_EDITOR=true git rebase --root --exec \
      "git commit --amend --reset-author --no-edit" >/dev/null
    echo "  re-authored all commits as $GH_USER"
  fi
else
  echo "  (keeping existing identity: $current_name <$current_email>)"
fi

# ------------------------------------------------------------- uncommitted --
if [[ -n "$(git status --porcelain)" ]]; then
  warn "You have uncommitted changes:"
  git status --short
  read -r -p "Commit them now as 'update before release'? [y/N] " ans
  if [[ "${ans,,}" == "y" ]]; then
    git add -A && git commit -m "update before release"
  else
    die "Commit or stash your changes first."
  fi
fi

# ------------------------------------------------------------------ remote --
if git remote get-url origin >/dev/null 2>&1; then
  say "Remote origin already set: $(git remote get-url origin)"
  git push -u origin main
else
  say "Creating GitHub repository $GH_USER/$REPO_NAME ($VISIBILITY)"
  gh repo create "$REPO_NAME" "$VISIBILITY" --source="$REPO_ROOT" --remote=origin --push
fi

# -------------------------------------------------------------------- tag ----
VERSION="$(python3 -c 'import re;print(re.search(r"VERSION = \"([^\"]+)\"", open("client/vozlab/__init__.py").read()).group(1))')"
TAG="v$VERSION"
say "Version in code: $VERSION"
if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "  tag $TAG already exists locally"
else
  git tag -a "$TAG" -m "VozLab $VERSION"
  echo "  created tag $TAG"
fi
git push origin "$TAG"

# --------------------------------------------------------------- feedback ---
cat <<EOF

$(printf '\033[1;32m')
  ┌──────────────────────────────────────────────────────────────┐
  │  Published!                                                  │
  └──────────────────────────────────────────────────────────────┘

  Repository : https://github.com/$GH_USER/$REPO_NAME
  Releases   : https://github.com/$GH_USER/$REPO_NAME/releases
  Build logs : https://github.com/$GH_USER/$REPO_NAME/actions

  GitHub Actions is now building VozLab-Setup-$VERSION.exe (a few minutes).
  Watch it with:   gh run watch
  When it finishes, download the installer from the Releases page and
  install it on your Windows laptop.
EOF
