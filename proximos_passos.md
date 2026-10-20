# Próximos passos da equipe

- [ ] **Revisar o [spec.md](spec.md)**, principalmente a localidade (seção 2), os parâmetros das culturas e dos solos (seção 5, conferindo no FAO-56) e os modelos (seção 8).
- [ ] **Resolver o `.gitattributes`**, que aparece como removido: restaurar com `git checkout -- .gitattributes` ou confirmar a remoção.
- [ ] **Fazer o primeiro commit** com `spec.md`, `todo.md`, este arquivo e o PDF do pré-projeto.
- [ ] **Executar o [todo.md](todo.md)** com o modelo de IA, fase por fase, conferindo a verificação de cada tarefa.
- [ ] **Conferir o resultado:**
  - [ ] `python -m pytest` passa.
  - [ ] `python app.py` abre e mostra uma recomendação.
  - [ ] `data/fonte_clima.txt` indica `nasa_power`, e não `sintetico`.
- [ ] **Escrever o relatório e os slides**, com a comparação dos 5 modelos (de `reports/metricas.csv`) e com as limitações: os rótulos são simulados e a acurácia mede concordância com o FAO-56, não validade agronômica.
- [ ] **Ensaiar a apresentação** sem internet.
