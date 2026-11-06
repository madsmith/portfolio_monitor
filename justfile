# Sync this skill into your local OpenClaw skills directory

set shell := ["zsh", "-cu"]

skill_name := "portfolio-manager"
dest := env_var('HOME') + "/.openclaw/skills/" + skill_name

# Copy/sync this folder to OpenClaw
install:
  mkdir -p "{{dest}}"
  rsync -a --delete \
    --exclude ".git/" \
    --exclude "justfile" \
    --exclude ".DS_Store" \
    --exclude "node_modules/" \
    --exclude "dist/" \
    --exclude "build/" \
    ./ "{{dest}}/"
