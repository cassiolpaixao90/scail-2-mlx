# Padrão de produção e validação de vídeos BillGym

Este procedimento organiza a substituição de personagens 3D por humanos fictícios
em vários exercícios. O movimento, a câmera, o enquadramento, o ritmo e o áudio
do original são o contrato de cada caso. Aparência plausível, por si só, não
aprova um vídeo. O primeiro teste de abdominal transferiu o movimento geral,
mas reprovou rosto, mãos, enquadramento e cenário; continua sendo uma referência
de falhas, não um modelo de qualidade aprovada.

## Organização dos arquivos

Cada exercício recebe uma pasta em `cases-local/`, fora do controle de versão.
O original é referenciado por caminho e hash; não é sobrescrito nem movido.

```text
cases-local/abdomen-03/
  case.json                       entradas e contrato do exercício
  inputs/                         máscaras, quadro editado, referências auxiliares
  preparation.md                  poses difíceis e decisões de preparação
  runs/
    r001-baseline/
      settings.json               parâmetros exatos e hipótese
      run.json                    registro imutável do candidato
      candidate.mp4               arquivo separado do original
      review/                     comparação sincronizada e detalhes ampliados
      visual-review.json          observações do responsável
      validation-v1.json          resultado técnico e elegibilidade
  delivery/                       apenas a versão aprovada para entrega
```

Uma nova configuração ou novo vídeo gerado recebe outro identificador. Uma nova
revisão recebe outro arquivo; mantenha a anterior para comparação. O utilitário
recusa substituir registros existentes. A entrega é uma escolha explícita, não
uma cópia ou publicação automática feita pelo utilitário.

## Etapas e critérios para avançar

| Etapa | Trabalho | Condição para avançar |
| --- | --- | --- |
| Cadastro | Ler vídeo inteiro, FPS, frames, dimensões, áudio e hashes | Arquivos legíveis e contrato conhecido |
| Preparação | Identificar poses críticas; preparar e revisar máscaras e referências | Corpo inteiro, câmera e correspondência do personagem corretos |
| Teste de execução `smoke` | Trecho pequeno para verificar carregamento, memória e saída | Processo estável; não aprova aparência nem entrega |
| Prévia `preview` | Trecho representativo, preferencialmente 3–5 segundos, com detalhe facial útil | Rosto, mãos, pose, câmera e continuidade aprovados |
| Candidato `final` | Vídeo completo na configuração validada | Mesma duração, FPS, proporção, áudio e revisão de todo o vídeo |
| Entrega | Conferir arquivos, relatório e responsável | Validação técnica e visual completas, sem pendências |

Uma prévia mais curta pode testar execução, mas não substitui a cobertura dos
movimentos difíceis. Se o exercício inteiro tiver menos de três segundos,
revise-o inteiro. Vídeos longos exigem revisar também as junções de segmentos.
O registro pode documentar uma tentativa reprovada; registrar não significa aprovar.

## Preparação específica de cada exercício

1. Classifique a posição: deitado, sentado, em pé ou suspensão. Anote câmera,
   direção do corpo, aparelhos, pontos de apoio e objetos que ocluem membros.
2. Marque os frames de início e fim, maior flexão/extensão, cruzamento dos braços,
   contato com equipamentos, perfil do rosto e qualquer membro escondido.
   O cadastro cria apenas amostras uniformes: refine `critical_source_frames`
   antes do primeiro registro de tentativa. Alterar o caso depois invalida os
   registros anteriores para aprovação, preservando-os como histórico.
3. Segmente a pessoa na imagem e em todo o vídeo. Revise mãos, dedos, pés,
   espaços entre braços/tronco e o contato com o chão. Nenhum polígono do
   abdominal atual é uma segmentação universal.
4. Defina o cenário de saída. O padrão é preservar o cenário do vídeo. Trocar
   para uma academia é uma variante criativa que exige um novo contrato,
   nunca uma mudança silenciosa causada pela referência de aparência.
5. Quando o motor aceitar um quadro de referência editado, use um frame do
   original para preservar pose e composição. Revise a imagem antes da geração.
   No SCAIL-2, uma referência já deitada é uma hipótese útil, não uma trava de pose.
6. Se a cena 3D original existir, considere aproveitar câmera e animação do rig
   como dados de controle. A compatibilidade depende do motor; não suponha que
   um MP4 contenha esses dados ou que todo modelo aceite profundidade/esqueleto.

## Regras por motor

| Motor | Preparação e limite relevante |
| --- | --- |
| SCAIL-2 | Usar modo e máscaras de substituição; cores devem corresponder ao mesmo personagem. Conferir semântica de fundo. LoRAs DPO e de iluminação exigem implementação compatível. |
| Port MLX atual | Substituição ainda precisa de validação contra a implementação oficial. Não atribuir toda falha ao modelo ou à foto. A integração de LoRA ainda não está implementada. |
| Wan-Animate | Revisar pose extraída e retargeting. As premissas do retargeting simplificado não se aplicam automaticamente a exercícios deitados. |
| Runway Edit Studio | Revisar o quadro editado antes de propagá-lo ao vídeo. Conferir acesso e custo na conta. No teste da conta atual, o plano gratuito bloqueou edição de vídeo. |

Uma referência próxima do rosto pode ajudar em motores com suporte a múltiplas
referências, mas deve ser testada: esse recurso é experimental no SCAIL-2 e pode
degradar a qualidade. Não transplante parâmetros, LoRAs ou regras entre modelos
apenas porque compartilham parte da arquitetura.

## Tentativas reproduzíveis

Antes da execução, preencha `settings.json` a partir do exemplo versionado:
motor, modelo, revisão dos pesos, commit, tamanho nativo, intervalo de frames,
seed quando disponível, sampler, passos, guidance, modo, prompt exato e arquivos
de condicionamento. Registre também hardware, versões de dependências e, depois
da execução, tempo, pico de memória ou custo em créditos. Não inclua credenciais.

Cada tentativa deve responder a uma hipótese: por exemplo, aumentar detalhe
facial mantendo todo o restante fixo. Seeds iguais em motores diferentes não
garantem ruído idêntico; uma comparação numérica exige controlar esse ruído.
Não invente revisões desconhecidas em registros históricos: marque-as como
desconhecidas e trate a reprodução exata como pendente.

Mantenha a qualidade nativa explícita. A exportação em 720×1280 de uma geração
288×512 não comprova detalhes em 720p. Rosto e dedos precisam ser distinguíveis
na resolução de inferência. Escolha resoluções compatíveis com cada motor,
preservando proporção por padding e removendo o padding na exportação.

## Revisão visual

Assista ao candidato inteiro em velocidade normal e lenta. Use pares de frames
sincronizados, detalhes do rosto e das mãos e as transições críticas do exercício.
Uma contact sheet ajuda a encontrar problemas, mas não comprova ausência de flicker.

| Critério no arquivo de revisão | O que observar |
| --- | --- |
| `identity_face` | Mesmo personagem; olhos, boca, nariz e contorno sem deformações ou mudanças bruscas |
| `hands_fingers` | Mãos, dedos, punhos e oclusões plausíveis durante as transições |
| `body_anatomy` | Sem membros extras/trocados; articulações e apoios coerentes |
| `pose_timing` | Tronco, cabeça, braços e pernas nas poses e instantes do original |
| `camera_framing` | Mesma perspectiva, escala e posição; corpo completo quando visível no original |
| `background` | Cenário contratado preservado e estável |
| `temporal_consistency` | Rosto, corpo, roupa e fundo sem saltos ou flicker ao assistir |
| `image_detail` | Detalhe nativo suficiente; ampliação não usada para esconder defeitos |
| `audio_sync` | Quando houver áudio, conteúdo e sincronização preservados |

Cada item recebe `pending`, `pass` ou `fail`, com uma observação concreta. Identifique
o responsável em `reviewer`. Uma revisão do agente não deve ser registrada como
aprovação do usuário. `watched_entire_clip` só pode ser verdadeiro depois de
assistir ao vídeo inteiro. Registre os índices dos frames realmente inspecionados,
incluindo início, fim e frames críticos que caem no trecho.

O validador vincula a revisão aos hashes do candidato e do registro da tentativa.
Confere fontes, condicionamentos, FPS, dimensões, contagem de frames e presença de
áudio. Em vídeos completos com áudio, compara o hash dos pacotes do primeiro
stream de áudio. Isso cobre o fluxo atual de cópia sem recodificação; conversões
de codec ou múltiplas faixas precisam de um procedimento adicional explícito.
O utilitário não mede automaticamente articulações nem identidade facial.

Para comparar uma prévia extraída do meio do exercício, passe
`--source-start-frame N` a `scripts/compare_candidate.py`, usando o mesmo índice
registrado em `settings.json`. Comparar o frame zero dessa prévia com o começo
do original produziria uma avaliação de movimento incorreta. O gerador MLX
atual recebe o trecho preparado como entrada; o cadastro não faz o recorte.

## Comandos de uso

Os comandos abaixo só cadastram e validam arquivos. Não carregam modelos, fazem
downloads ou geram vídeo. Execute na raiz do fork com o ambiente já configurado.

```sh
rtk proxy .venv/bin/python scripts/video_case.py init \
  --case cases-local/exercicio-01 --name 'Nome do exercício' \
  --source /caminho/original.mp4 --reference /caminho/personagem.png

# Preparar inputs, preencher settings.json e executar o motor autorizado.
# O candidato deve ser um arquivo novo. Depois registrar:
rtk proxy .venv/bin/python scripts/video_case.py record \
  --case cases-local/exercicio-01 --run r001-baseline --stage preview \
  --candidate /caminho/candidate.mp4 --settings /caminho/settings.json

rtk proxy .venv/bin/python scripts/video_case.py review-template \
  --case cases-local/exercicio-01 --run r001-baseline \
  --output cases-local/exercicio-01/runs/r001-baseline/visual-review.json

# Preencher a revisão a partir da inspeção real. Para medir apenas o técnico,
# omitir --review; a validação visual continuará pendente.
rtk proxy .venv/bin/python scripts/video_case.py validate \
  --case cases-local/exercicio-01 --run r001-baseline \
  --review cases-local/exercicio-01/runs/r001-baseline/visual-review.json \
  --output cases-local/exercicio-01/runs/r001-baseline/validation-v1.json
```

`eligible_for_delivery` só será verdadeiro para uma tentativa `final` de duração
completa com validações técnica e visual aprovadas. Um resultado falso não apaga
o candidato. Revise os itens reprovados e crie outra tentativa; não modifique o
original nem os resultados para fazer a validação passar.

Em automações de entrega, acrescente `--require-delivery` ao comando `validate`:
ele retorna código 2 quando o candidato não é elegível. Sem essa opção, código
0 indica apenas que o relatório foi produzido, não que o vídeo foi aprovado.

## Recursos e otimização

Use os limites e a autorização vigentes para processamento local ou remoto.
Mantenha um único teste pesado por vez, supervisão de RAM/swap, prazo explícito
e arquivos de log. O limite de memória MLX é orientativo; o supervisor é necessário.
Ao concluir, confirme o término do processo e registre o espaço ocupado pelos pesos.

Depois de obter uma prévia aprovada, meça separadamente preparação, encoders,
passagens do modelo, VAE e exportação. Teste uma otimização por vez e repita a
mesma revisão visual. Compare tempo total, memória e custo por segundo útil de
vídeo aprovado. Quantização, redução de passos, cache e LoRAs de aceleração são
experimentos, não ganhos garantidos. Conserve sempre a configuração de qualidade
aprovada como referência para regressões.

## Fontes e manutenção

Revisado em 14 de outubro de 2026. Revalide recomendações ao trocar versão,
modelo ou motor, sem substituir as medições do nosso caso por benchmarks externos.

- [SCAIL-2 e preparação oficial](https://github.com/zai-org/SCAIL-2)
- [Estado do port MLX](https://github.com/xocialize/scail-2-mlx)
- [Preparação Wan-Animate](https://github.com/Wan-Video/Wan2.2/blob/main/wan/modules/animate/preprocess/UserGuider.md)
- [Runway Edit Studio](https://help.runwayml.com/hc/en-us/articles/51683104370451-Creating-with-Edit-Studio)
- [Resultado do primeiro caso](../BILLGYM-VALIDATION.md)
