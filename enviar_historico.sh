#!/data/data/com.termux/files/usr/bin/bash
# Baixa 5 anos de preços mensais pelo celular (o Yahoo bloqueia o GitHub) e envia ao GitHub.
# Rode uma vez agora e depois de vez em quando (1x por mês basta).
cd ~/cotacoes || exit 1
git pull --rebase -X theirs
python3 atualizar_cotacoes.py historico
git add hist_celular.json
git diff --staged --quiet || (git commit -m "historico de precos do celular" && git pull --rebase -X theirs && git push)
gh workflow run cotacoes.yml
echo "Pronto. Em ~2 minutos o cotacoes.json terá a valorização dos ativos."
