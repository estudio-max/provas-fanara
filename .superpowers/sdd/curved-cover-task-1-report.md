# Curved Cover — Task 1 Report

## Escopo entregue

- Definido o contrato de estilos `("mosaico", "curvas_editoriais")` em
  `provas.capas`, mantendo `ESTILOS` como alias de compatibilidade.
- Adicionada `validate_cover_style`, com a mensagem PT-BR exigida.
- Elevado o formato de projetos para schema v2, com migração não mutável de
  v1 que adiciona `estilo_capa="mosaico"` somente quando ausente.
- A validação é aplicada na configuração renderizada por `Config.com_padroes`
  e no snapshot persistente `ProjectConfig`.

Não foi alterada geometria, renderização, UI, miolo, orientação A4 nem o
tratamento de referências de identidade no JSON.

## TDD

RED executado antes do código de produção:

```text
python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q
4 failed, 26 passed
```

As falhas verificaram schema v2/migração e rejeição PT-BR de estilo inválido.
Houve inicialmente uma referência ausente a `Config` em um teste novo; ela foi
corrigida no teste e o RED foi repetido, ficando somente as quatro falhas de
comportamento esperado.

GREEN após a implementação mínima:

```text
python -m pytest tests/test_projeto.py tests/test_motor_editorial.py -q
30 passed
```

Cobertura adicionada: migração de v1 preservando `estudio`, `site` e `logo`;
persistência de `curvas_editoriais`; validação de estilo inválido por ambas as
fronteiras de configuração; e rejeição de schema futuro atualizada para v3.

## Suíte e revisão

```text
python -m pytest -q
153 passed (exit 0, 296.5 s)

git diff --check
exit 0
```

Revisão do diff: a migração copia tanto o payload quanto `config`, evitando
mutar o JSON recebido; v1 ganha apenas o novo padrão; v2 preserva
`curvas_editoriais`; versões diferentes de v1/v2 continuam rejeitadas. O
alias `ESTILOS` aponta exatamente para o novo contrato.

## Preocupações

- A suíte completa é lenta neste ambiente (296,5 s); a primeira tentativa com
  limite de 120 s expirou sem falhas. A execução completa posterior concluiu
  com exit 0.
- Os renderizadores legados para estilos históricos permanecem no módulo, mas
  não são expostos pelo novo contrato e a nova validação os impede pelas vias
  de configuração previstas. Removê-los ou desenhar `curvas_editoriais` fica
  explicitamente fora desta tarefa.
