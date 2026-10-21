#!/data/data/com.termux/files/usr/bin/bash
# Busca os dividendos pelo celular (que o Yahoo/StatusInvest não bloqueiam) e envia ao GitHub.
cd ~/cotacoes || exit 1
git pull --rebase -X theirs
python3 atualizar_cotacoes.py dividendos --forcar
git add div_celular.json
git diff --staged --quiet || (git commit -m "dividendos do celular" && git pull --rebase -X theirs && git push)
gh workflow run cotacoes.yml
echo "Pronto. Em ~2 minutos o cotacoes.json terá os dividendos."
