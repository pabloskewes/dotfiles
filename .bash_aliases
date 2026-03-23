alias force-pull='git reset --hard origin/$(git rev-parse --abbrev-ref HEAD) && git pull'
alias eslint='pnpm exec eslint . -c .eslintrc.cjs --ext .ts,.js,.cjs,.vue,.tsx,.jsx'