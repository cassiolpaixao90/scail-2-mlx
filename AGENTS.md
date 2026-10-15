# Trabalho com vídeos BillGym

Leia `docs/VIDEO-WORKFLOW.md` antes de preparar, gerar ou avaliar um novo caso.
Use `scripts/video_case.py` para registrar entradas, tentativas e revisões.

- Preserve os originais. Cada tentativa recebe identificador e candidato novos.
- Mantenha mídias, caminhos pessoais e pesos em `cases-local/`, `validation-local/`
  ou `weights/`, que são ignorados pelo Git. Não publique esses arquivos no fork.
- Separe teste de execução, prévia de qualidade e candidato completo.
  Metadados corretos não aprovam rosto, mãos, movimento ou estabilidade temporal.
- Não reaproveite o polígono ou os limiares de `prepare_billgym_case.py` em
  outros personagens/exercícios sem nova segmentação e inspeção.
- Registre observações reais. Não atribua aprovação ao usuário sem ela existir.
  Uma revisão feita pelo agente deve identificar o agente como responsável.
- Respeite a autorização de processamento local/remoto e os limites de recursos
  já vigentes na conversa. Não peça novamente autorização já concedida.
  Padronizar, inspecionar e registrar não implica iniciar novas gerações ou downloads.
- Compare qualidade antes de otimizar velocidade; altere uma variável por tentativa.
- Ao concluir, informe candidato, comparação, resolução nativa, duração real,
  modelo/configuração, tempo/custo e reprovações. Um arquivo ampliado não adquire
  a qualidade nativa da resolução de exportação.

As instruções mais recentes do usuário prevalecem sobre este procedimento.
