"""Base de conhecimento do assistente VIA: respostas do produto, em português,
escritas sobre o que o VIA realmente faz hoje (não prometem nada que não exista).

Cada artigo tem `keywords`: pares (trecho, peso). O trecho é comparado, sem acento e em
minúsculas, como pedaço do texto da pergunta (então "cadastr" pega cadastrar/cadastro).
Pesos altos (6-7) são frases específicas; baixos (1.5-3) são palavras soltas.

`answer` é um texto ou uma função(conta) -> texto, para respostas personalizadas
(ex.: o plano e o consumo da organização de quem pergunta).

Se o produto mudar (preços, recursos, telas), atualize aqui: é a única fonte.
"""

from dataclasses import dataclass, field
from typing import Callable, List, Tuple, Union


@dataclass
class Article:
    id: str
    title: str
    keywords: List[Tuple[str, float]]
    answer: Union[str, Callable]
    related: List[str] = field(default_factory=list)


def _limit(value, singular=None):
    return "ilimitado(a)" if value is None else str(value)


def _used(used, limit):
    return f"{used} de {limit}" if limit is not None else f"{used} (sem limite)"


def _meu_plano(account):
    if not account:
        return (
            "Os limites dependem do plano da sua organização. Veja o seu plano, o consumo do mês e os recursos "
            "incluídos em Configurações → Plano e uso."
        )
    limits, usage = account["limits"], account["usage"]
    status = {"active": "ativo", "inactive": "suspenso", "expired": "expirado"}.get(account["status"], account["status"])
    due = f", vence em {account['expires']}" if account.get("expires") else ""
    lines = [
        f"Seu plano é o {account['plan_label']} ({status}{due}).",
        f"• Câmeras: {_used(usage['cameras'], limits['max_cameras'])}",
        f"• Usuários: {_used(usage['users'], limits['max_users'])}",
        f"• Relatórios em PDF neste mês: {_used(usage['pdf'], limits['pdf_per_month'])}",
    ]
    chat = limits["chat_per_month"]
    if chat == 0:
        lines.append("• Assistente VIA (consultas aos dados): não incluído no plano")
    else:
        lines.append(f"• Consultas de dados ao assistente neste mês: {_used(usage['chat'], chat)} (dúvidas de uso, como esta, não contam)")
    lines.append("")
    lines.append("O consumo de relatórios e consultas zera no início de cada mês. Para ampliar o plano, abra um chamado em Configurações → Ajuda e privacidade.")
    return "\n".join(lines)


ARTICLES: List[Article] = [
    Article(
        "o_que_e_via", "O que é o VIA",
        [("o que e o via", 6), ("o que e a via", 6), ("o que e isso", 3), ("para que serve", 5), ("como funciona o via", 6),
         ("o que o via faz", 6), ("sobre o via", 5), ("bom app", 5), ("vale a pena", 4), ("explica o via", 5),
         ("quem e o via", 5), ("apresent", 2.5), ("o que e vc", 3), ("como o via funciona", 6)],
        "O VIA transforma imagens de câmeras de trânsito em dados para apoiar decisões sobre mobilidade urbana.\n\n"
        "O caminho é: câmera → IA → dados → relatório. A IA identifica e conta carros, motos, ônibus, caminhões e pessoas, "
        "e o VIA organiza isso em:\n"
        "• Estatísticas: total, pico de movimento e hora mais movimentada;\n"
        "• Relatórios em PDF, com todo o detalhamento;\n"
        "• Mapa das câmeras no seu município;\n"
        "• este assistente, que responde sobre os dados e tira dúvidas de uso.\n\n"
        "O VIA só mostra o que foi realmente registrado pelas câmeras: não estima o que faltou.",
        ["Como cadastro uma câmera?", "O que o assistente consegue fazer?"],
    ),
    Article(
        "assistente", "O que o assistente faz",
        [("o que voce faz", 6), ("o que voce consegue", 6), ("o que o assistente", 6), ("o que a via consegue", 5),
         ("quem e voce", 6), ("quem e vc", 6), ("voce e uma ia", 6), ("voce e um robo", 5), ("como te uso", 5),
         ("como usar o assistente", 6), ("o que posso perguntar", 6), ("me ajuda", 3), ("ajuda", 1.6),
         ("o que eu posso pedir", 5), ("quais perguntas", 5), ("exemplos de pergunta", 5), ("voce responde", 4)],
        "Eu sou o assistente da VIA. Posso:\n"
        "• consultar os dados das suas câmeras: fluxo, horário de pico, tipos de veículo, ocorrências e comparação entre períodos "
        "(ex.: “Qual foi o horário de pico ontem?”, “Compare 8h às 10h com 14h às 16h”);\n"
        "• tirar dúvidas de uso: câmeras, mapa, relatórios, plano, equipe e privacidade.\n\n"
        "Lembro do contexto da conversa (“e as ocorrências?” usa o mesmo período) e só uso números registrados: não invento valores. "
        "Suas conversas ficam salvas na lista ao lado.",
        ["Como cadastro uma câmera?", "Qual é o meu plano?"],
    ),
    Article(
        "cadastrar_camera", "Como cadastrar uma câmera",
        [("cadastrar camera", 6), ("cadastrar uma camera", 6), ("cadastro uma camera", 6), ("cadastro de camera", 6),
         ("adicionar camera", 6), ("adicionar uma camera", 6), ("adiciono uma camera", 6), ("colocar camera", 5),
         ("colocar uma camera", 5), ("incluir camera", 5), ("nova camera", 5), ("registrar camera", 5), ("registrar uma camera", 5),
         ("conectar camera", 5), ("conectar uma camera", 5), ("conecto a camera", 5), ("configurar camera", 5),
         ("instalar camera", 4), ("como coloco", 3)],
        "Para cadastrar uma câmera:\n"
        "1. Abra a aba Câmeras e clique em Adicionar câmera;\n"
        "2. Dê um nome à câmera (ex.: “Acesso principal”);\n"
        "3. Informe o endereço onde ela está (rua, número e bairro). É o endereço que coloca a câmera no mapa: o computador que "
        "monitora não precisa estar no local;\n"
        "4. Escolha a fonte do vídeo e, quando for o caso, informe a URL do stream.\n\n"
        "Em contas de clientes a URL precisa ser de rede pública (rtsp://, http:// ou https://); endereços de rede interna não são aceitos. "
        "O seu plano define quantas câmeras você pode ter: pergunte “qual é o meu plano?” para ver o limite.",
        ["Por que minha câmera dá falha na conexão?", "Como a câmera aparece no mapa?"],
    ),
    Article(
        "camera_falha", "Câmera com falha de conexão",
        [("falha na conexao", 6), ("falha de conexao", 6), ("camera nao conecta", 6), ("camera nao conectou", 6),
         ("nao conecta", 5), ("nao conectou", 5), ("sem sinal", 5), ("camera offline", 5), ("camera fora do ar", 5),
         ("nao aparece a imagem", 5), ("sem imagem", 5), ("tela preta", 5), ("erro na camera", 5), ("camera com erro", 5),
         ("conectando transmissao", 5), ("camera travada", 4), ("manifestloaderror", 5), ("nao abre a camera", 5),
         ("nao consigo conectar", 5), ("camera nao funciona", 5)],
        "“Falha na conexão” significa que o VIA não conseguiu receber o vídeo daquela câmera. As causas mais comuns:\n"
        "• a URL do stream está incorreta ou incompleta, ou a câmera está desligada/sem internet;\n"
        "• o stream exige usuário e senha (inclua as credenciais na URL, se for o caso);\n"
        "• RTSP: o navegador não reproduz RTSP direto, é preciso um gateway que converta para HLS ou WebRTC;\n"
        "• a câmera está numa rede interna: contas de clientes só aceitam URL pública;\n"
        "• firewall ou operadora bloqueando a porta do stream.\n\n"
        "Teste a URL num player (como o VLC) para confirmar que ela funciona; depois exclua e cadastre a câmera de novo. "
        "Se continuar, abra um chamado em Ajuda e privacidade informando o tipo e o modelo da câmera.",
        ["Quais câmeras funcionam com o VIA?"],
    ),
    Article(
        "endereco_mapa", "Como a câmera aparece no mapa",
        [("camera no mapa", 6), ("camera nao aparece no mapa", 7), ("aparece no mapa", 5), ("endereco da camera", 6),
         ("alterar endereco", 6), ("mudar endereco", 6), ("trocar endereco", 6), ("corrigir endereco", 6),
         ("posicao da camera", 6), ("onde fica a camera", 5), ("camera sem endereco", 6), ("nao achou o endereco", 6),
         ("nao encontrou o endereco", 6), ("nao encontrei o endereco", 6), ("localizar camera", 5), ("como funciona o mapa", 6),
         ("pino", 4), ("alfinete", 4), ("mapa", 1.8)],
        "O mapa mostra somente as câmeras já cadastradas na aba Câmeras. A posição vem do endereço digitado no cadastro: o VIA localiza o "
        "endereço dentro do município escolhido e a câmera já aparece no ponto.\n"
        "• Para corrigir, abra o pino da câmera no mapa e use Alterar endereço (ou use a lista “Câmeras sem endereço no mapa”, abaixo do mapa);\n"
        "• se o endereço não for encontrado, informe rua, número e bairro;\n"
        "• o alfinete no canto do mapa volta ao seu município;\n"
        "• o computador que monitora não precisa estar perto da câmera.",
        ["Como troco o município do mapa?"],
    ),
    Article(
        "municipio", "Município do mapa",
        [("trocar municipio", 6), ("mudar municipio", 6), ("alterar municipio", 6), ("outra cidade", 5), ("mudar de cidade", 5),
         ("trocar de cidade", 5), ("municipio do mapa", 6), ("estado e municipio", 6), ("escolher municipio", 6),
         ("outro municipio", 5), ("cidade do mapa", 5), ("municipio", 2), ("cidade", 1.6)],
        "O estado e o município são pedidos só na primeira vez que você entra. Para trocar depois: Configurações → Perfil → Município do mapa, "
        "ou o botão Trocar município no cartão do mapa (Visão geral). O mapa passa a abrir centrado no município escolhido, com o "
        "contorno oficial dele (dados do IBGE).",
    ),
    Article(
        "planos", "Planos do VIA",
        [("quais planos", 6), ("quais sao os planos", 6), ("tipos de plano", 6), ("planos do via", 6),
         ("diferenca entre os planos", 7), ("diferenca dos planos", 7), ("plano report", 6), ("plano insight", 6),
         ("plano intelligence", 6), ("plano business", 6), ("via report", 6), ("via insight", 6), ("via intelligence", 6),
         ("via business", 6), ("report e insight", 5), ("planos", 3)],
        "O VIA tem quatro planos:\n"
        "• VIA Report: estudo pontual (coleta, análise e relatório final) para quem precisa de dados de um período específico;\n"
        "• VIA Insight: estudo aprofundado, com mais pontos de análise e comparativos;\n"
        "• VIA Intelligence: plataforma recorrente para profissionais e equipes (estatísticas, assistente, relatórios e histórico);\n"
        "• VIA Business: para empresas de engenharia e organizações com maior volume de câmeras, usuários e relatórios.\n\n"
        "Os valores são definidos sob orçamento, conforme câmeras, período, usuários e consumo. Para contratar ou ampliar, abra um chamado em "
        "Ajuda e privacidade. Para ver o que o seu plano atual inclui, pergunte “qual é o meu plano?”.",
        ["Qual é o meu plano?", "Como contrato ou amplio o plano?"],
    ),
    Article(
        "meu_plano", "Seu plano e consumo",
        [("meu plano", 7), ("qual e o meu plano", 7), ("qual meu plano", 7), ("meu limite", 6), ("limite do plano", 6),
         ("limites do plano", 6), ("meus limites", 6), ("o que meu plano inclui", 7), ("o que o meu plano", 6),
         ("quantas cameras posso", 7), ("quantos usuarios posso", 7), ("quantos relatorios posso", 7),
         ("quantos relatorios ainda", 7), ("quantos relatorios restam", 7), ("quantas perguntas posso", 7),
         ("quanto ja usei", 6), ("meu consumo", 6), ("meu uso", 5), ("minha assinatura", 6), ("vencimento", 5),
         ("quando vence", 6), ("plano vence", 6), ("plano expira", 6), ("limite de cameras", 6), ("limite de usuarios", 6),
         ("limite de relatorios", 6), ("limite mensal", 6), ("creditos", 5), ("estou no plano", 6), ("em que plano", 6)],
        _meu_plano,
        ["Como contrato ou amplio o plano?"],
    ),
    Article(
        "ampliar_plano", "Contratar ou ampliar o plano",
        [("contratar", 6), ("como contrato", 6), ("quero contratar", 6), ("assinar", 5), ("como assino", 6), ("ampliar plano", 6),
         ("ampliar o plano", 6), ("aumentar plano", 6), ("aumentar limite", 6), ("mais cameras", 5), ("mais relatorios", 5),
         ("mais usuarios", 5), ("upgrade", 5), ("mudar de plano", 6), ("trocar de plano", 6), ("fazer orcamento", 6),
         ("orcamento", 5), ("quanto custa", 6), ("qual o preco", 6), ("preco", 5), ("valor do plano", 6), ("valores", 3.5),
         ("pagamento", 5), ("como pago", 6), ("nota fiscal", 5), ("boleto", 5), ("cartao", 3), ("assinatura", 3)],
        "Os valores e as condições são definidos sob orçamento, conforme o número de câmeras, o período de coleta, os usuários e o consumo. "
        "Para contratar ou ampliar o plano (mais câmeras, usuários ou relatórios), abra um chamado em Configurações → Ajuda e privacidade → "
        "Abrir chamado (ou pelo botão Contato / Suporte) e a equipe da VIA retorna com a proposta. No momento não há cobrança automática dentro do app.",
    ),
    Article(
        "relatorios", "Relatórios em PDF",
        [("como gerar relatorio", 7), ("gerar relatorio", 6), ("gerar um relatorio", 6), ("como exportar", 6), ("exportar relatorio", 6),
         ("exportar pdf", 6), ("baixar relatorio", 6), ("baixar o relatorio", 6), ("relatorio pdf", 6), ("relatorio em pdf", 6),
         ("o que tem no relatorio", 7), ("o que vem no pdf", 7), ("conteudo do relatorio", 7), ("tirar relatorio", 5),
         ("fazer um relatorio", 6), ("emitir relatorio", 6), ("relatorios", 3), ("pdf", 3)],
        "Para gerar um relatório: abra Relatórios, escolha o período (Hoje, 7 ou 30 dias, ou datas livres), o horário (opcional) e a câmera, "
        "e clique em Exportar PDF.\n\n"
        "O PDF traz o detalhamento completo:\n"
        "• total de veículos e distribuição por tipo;\n"
        "• fluxo por dia e por horário, com os picos;\n"
        "• detalhamento por câmera;\n"
        "• comparação com o período anterior (quando há dados comparáveis);\n"
        "• ocorrências registradas.\n\n"
        "Cada PDF exportado usa 1 do limite mensal do plano; pergunte “quantos relatórios ainda posso gerar?” para ver o seu saldo. "
        "Em Estatísticas você vê só o resumo: o detalhe completo fica no relatório.",
        ["Qual é o meu plano?", "Por que as estatísticas estão desfocadas?"],
    ),
    Article(
        "estatisticas", "Estatísticas x Relatórios",
        [("por que esta desfocado", 7), ("por que esta desfocada", 7), ("desfocado", 6), ("desfocada", 6), ("borrado", 6),
         ("embacado", 6), ("travado", 4), ("bloqueado", 4), ("baixe o relatorio", 7), ("por que nao vejo", 6),
         ("nao consigo ver os graficos", 7), ("graficos", 4), ("grafico", 4), ("analise detalhada", 6),
         ("diferenca entre estatisticas e relatorios", 8), ("onde vejo os graficos", 7), ("estatisticas", 2.5)],
        "Em Estatísticas você acompanha o resumo do período (24 horas, 7 dias ou 30 dias): fluxo total, pico de movimento e hora mais "
        "movimentada, além das contagens ao vivo por câmera. A análise detalhada (evolução, perfil por horário, mapa de calor semanal, fluxo "
        "por câmera e janelas de maior movimento) aparece desfocada de propósito: o detalhamento completo vem no relatório em PDF, em Relatórios. "
        "Assim os números detalhados ficam no documento que você exporta e compartilha.",
        ["Como gero um relatório?"],
    ),
    Article(
        "definicoes", "O que significam os indicadores",
        [("o que significa", 6), ("o que quer dizer", 6), ("o que e fluxo", 7), ("o que e pico", 7), ("o que e janela", 7),
         ("o que e hora mais movimentada", 7), ("como e calculado", 6), ("calculad", 3.5), ("como calcula", 6),
         ("como voces calculam", 6), ("como funciona o pico", 7), ("fluxo total", 4), ("pico de movimento", 4),
         ("hora mais movimentada", 4), ("janela de 15", 6), ("definicao", 5), ("significa", 3.5), ("conta pessoas", 5),
         ("conta pedestres", 5), ("pessoas contam", 5), ("pessoa conta como veiculo", 6), ("veiculos unicos", 6),
         ("conta o mesmo carro", 6), ("contagem dupla", 6), ("como contam", 6), ("como conta", 6), ("como e feita a contagem", 7)],
        "• Fluxo total: quantos objetos únicos a IA registrou no período. Cada veículo é rastreado e contado uma vez, mesmo aparecendo em vários "
        "quadros. O total soma todos os tipos detectados (carro, moto, ônibus, caminhão e também pessoas); o detalhamento por tipo mostra cada um;\n"
        "• Pico de movimento: a janela de 15 minutos com mais registros;\n"
        "• Hora mais movimentada: a hora do dia (horário de Brasília) com a maior soma no período;\n"
        "• Janela: bloco de 15 minutos usado para agrupar as contagens.\n\n"
        "Os períodos de 24 horas, 7 e 30 dias são contados de agora para trás.",
        ["Os dados são precisos?"],
    ),
    Article(
        "precisao", "Precisão dos dados",
        [("quao preciso", 7), ("e preciso", 6), ("e confiavel", 7), ("confiavel", 5), ("confianca dos dados", 7), ("acuracia", 6),
         ("margem de erro", 7), ("pode errar", 6), ("os dados estao certos", 7), ("dados corretos", 6), ("qual a precisao", 7),
         ("qualidade da contagem", 6), ("precisao", 5), ("erra", 3.5), ("acerta", 3.5), ("confio nos dados", 7)],
        "A contagem é feita por visão computacional (IA) e a precisão depende da câmera: qualidade da imagem, ângulo, iluminação, distância e "
        "clima. Em boas condições a detecção é consistente, mas nenhuma contagem automática é perfeita: veículos pequenos, parcialmente "
        "encobertos ou à noite com pouca luz podem falhar.\n\n"
        "O que o VIA faz para manter a confiança:\n"
        "• conta cada veículo uma vez (rastreamento);\n"
        "• mostra “sem leitura” quando não há dados, em vez de estimar;\n"
        "• o congestionamento é uma estimativa heurística, que depende de calibração por câmera;\n"
        "• há um processo de aprendizado controlado, com revisão humana dos casos de baixa confiança.\n\n"
        "Para decisões técnicas importantes, recomendamos validar uma amostra manualmente. Se quiser, abra um chamado para combinarmos uma validação.",
    ),
    Article(
        "sem_dados", "Por que aparece zero ou 'sem leitura'",
        [("sem leitura", 7), ("sem dados", 7), ("nenhuma leitura", 7), ("esta zerado", 7), ("zerado", 6), ("zero veiculos", 7),
         ("por que zero", 7), ("nao tem dados", 7), ("nao aparece nada", 6), ("nao ha dados", 7), ("nada aparece", 6),
         ("dados nao aparecem", 7), ("por que nao tem dados", 7), ("nao carregam os dados", 6), ("nao mostra nada", 6)],
        "“Sem leitura” (ou zero) significa que nenhuma câmera registrou veículos naquele período. Pode ser que a câmera estivesse desligada ou "
        "sem conexão, que não tenha passado ninguém, ou que a câmera ainda não esteja cadastrada. O VIA mostra só o que foi realmente "
        "registrado: não estima nem preenche o que faltou.\n\n"
        "Confira na aba Câmeras se a câmera está online. Se ela mostra “Falha na conexão”, pergunte “por que minha câmera dá falha na conexão?”.",
        ["Por que minha câmera dá falha na conexão?"],
    ),
    Article(
        "ocorrencias", "O que são ocorrências",
        [("o que sao ocorrencias", 7), ("o que e ocorrencia", 7), ("como detecta congestionamento", 7), ("como detectam congestionamento", 7),
         ("como o congestionamento", 7), ("o que e congestionamento", 7), ("tipos de ocorrencia", 7), ("quais ocorrencias", 6),
         ("detecta acidente", 7), ("detecta alagamento", 7)],
        "Ocorrências são eventos de trânsito que o VIA detecta e registra, com horário e câmera:\n"
        "• congestionamento iniciado e encerrado (estimativa heurística, que depende de calibração);\n"
        "• veículo parado.\n"
        "Você vê as ocorrências ao vivo em Estatísticas → Ocorrências. Acidentes e alagamentos não são criados automaticamente: só entram "
        "se houver detecção ou integração externa. Para eu consultar, pergunte por exemplo “houve alguma ocorrência hoje?”.",
    ),
    Article(
        "privacidade", "Privacidade e LGPD",
        [("lgpd", 7), ("privacidade", 7), ("dados pessoais", 7), ("reconhecimento facial", 8), ("reconhece rosto", 7),
         ("reconhece pessoas", 7), ("identifica pessoas", 7), ("identifica placas", 6), ("le placa", 6), ("grava video", 7),
         ("grava imagem", 7), ("guarda video", 7), ("armazena video", 7), ("guarda imagens", 7), ("termos de uso", 6),
         ("politica de privacidade", 8), ("compartilha dados", 7), ("dados compartilhados", 7), ("quem ve meus dados", 8),
         ("outros clientes veem", 7), ("anonimiz", 6), ("remover meus dados", 7), ("apagar meus dados", 7),
         ("excluir meus dados", 7), ("direitos do titular", 7)],
        "Como o VIA trata vídeo e dados:\n"
        "• o vídeo é processado no servidor para contar veículos e pessoas e estimar o fluxo. Não há reconhecimento facial nem identificação "
        "de pessoas específicas;\n"
        "• no histórico ficam apenas dados agregados (contagens por tipo, horários, ocorrências). Os quadros de vídeo não são gravados de forma "
        "permanente; a exceção são amostras usadas no aprendizado controlado do modelo, quando ativo, que passam por revisão humana antes de qualquer uso;\n"
        "• os dados de cada organização são isolados: outros clientes não enxergam os seus, e as conversas com este assistente são privadas de cada usuário;\n"
        "• os dados não são compartilhados com terceiros fora da operação do sistema.\n\n"
        "Para pedir informação, correção ou remoção de dados, abra um chamado em Ajuda e privacidade.",
    ),
    Article(
        "seguranca", "Segurança da conta",
        [("e seguro", 6), ("seguranca", 6), ("meus dados estao seguros", 8), ("proteg", 3.5), ("vazamento", 6), ("hackear", 5),
         ("alguem acessar", 6), ("invadir", 5)],
        "O acesso é por e-mail e senha, com limite de tentativas, sessões protegidas e desconexão dos outros dispositivos quando você troca a senha. "
        "Cada organização enxerga somente os próprios dados. Dicas: use uma senha longa e exclusiva (Configurações → Segurança) e desative usuários "
        "que saíram da equipe (Configurações → Equipe).",
    ),
    Article(
        "equipe", "Equipe e usuários",
        [("adicionar usuario", 7), ("cadastrar usuario", 7), ("criar usuario", 7), ("novo usuario", 7), ("convidar", 6),
         ("adicionar pessoa", 6), ("adicionar alguem", 6), ("equipe", 3), ("usuarios", 3), ("desativar usuario", 7),
         ("remover usuario", 7), ("quem pode", 4), ("permissoes", 6), ("responsavel da organizacao", 6), ("administrador", 4),
         ("colegas", 5), ("compartilhar com", 4), ("dar acesso", 7)],
        "O responsável da organização gerencia a equipe em Configurações → Equipe: pode adicionar usuários (com e-mail, nome e uma senha inicial, "
        "que a pessoa troca depois em Segurança), desativar quem saiu e reativar quando precisar. O número de usuários depende do plano. Todos os "
        "usuários da organização veem as mesmas câmeras, estatísticas e relatórios; as conversas com o assistente são privadas de cada pessoa. "
        "Usuários comuns não gerenciam a equipe.",
    ),
    Article(
        "senha", "Senha e acesso",
        [("esqueci a senha", 8), ("esqueci minha senha", 8), ("recuperar senha", 8), ("redefinir senha", 8), ("resetar senha", 8),
         ("trocar senha", 8), ("trocar a senha", 8), ("alterar senha", 8), ("mudar senha", 8), ("mudar a senha", 8),
         ("nao consigo entrar", 7), ("nao consigo logar", 7), ("nao consigo acessar", 6), ("login", 3), ("senha", 4.5),
         ("conta bloqueada", 6), ("conta suspensa", 6)],
        "Para trocar a senha: Configurações → Segurança → Alterar senha (informe a senha atual; os outros dispositivos são desconectados). "
        "Se você esqueceu a senha, no momento ela é redefinida pela equipe da VIA: abra um chamado ou entre em contato. "
        "Se aparecer “Conta suspensa” ou “plano expirado”, também fale com a VIA.",
    ),
    Article(
        "perfil_foto", "Perfil e foto",
        [("trocar foto", 8), ("mudar foto", 8), ("alterar foto", 8), ("foto de perfil", 8), ("colocar foto", 8),
         ("trocar nome", 7), ("mudar nome", 7), ("alterar nome", 7), ("trocar email", 7), ("mudar email", 7),
         ("alterar email", 7), ("perfil", 3.5), ("minha foto", 7)],
        "Em Configurações → Perfil você altera o nome e a foto (JPG, PNG ou WebP, até 3 MB; a imagem é ajustada para um quadrado) e escolhe o "
        "município do mapa. O e-mail de acesso não é editável por você: para trocá-lo, peça à equipe da VIA.",
    ),
    Article(
        "conversas", "Conversas do assistente",
        [("historico de conversas", 8), ("apagar conversa", 8), ("excluir conversa", 8), ("renomear conversa", 8),
         ("nova conversa", 7), ("minhas conversas", 7), ("conversas salvas", 7), ("alguem ve minhas conversas", 8),
         ("conversa privada", 7), ("conversas", 3.5)],
        "As conversas com o assistente ficam salvas na lista ao lado (no celular, no botão de menu do chat). Clique em Nova conversa para começar "
        "outra e passe o mouse sobre uma conversa para renomear ou excluir. Elas são privadas: o app não mostra as suas conversas a outros "
        "usuários, nem da sua organização.",
    ),
    Article(
        "suporte", "Falar com a equipe",
        [("suporte", 7), ("falar com a equipe", 8), ("falar com alguem", 7), ("atendimento", 7), ("abrir chamado", 8),
         ("chamado", 6), ("contato", 5), ("reclamar", 6), ("sugestao", 5), ("ouvidoria", 6), ("telefone", 6), ("whatsapp", 6),
         ("email de suporte", 7), ("falar com um humano", 8), ("falar com atendente", 8), ("falar com uma pessoa", 8)],
        "Você pode falar com a equipe da VIA pelo botão Contato / Suporte (no rodapé do painel e no menu da conta) ou em Configurações → "
        "Ajuda e privacidade → Abrir chamado. Escolha a categoria (manutenção, erro, sugestão ou outro) e descreva o que aconteceu.",
    ),
    Article(
        "compatibilidade", "Quais câmeras funcionam",
        [("quais cameras funcionam", 8), ("quais cameras posso usar", 8), ("quais cameras sao compativeis", 8), ("quais cameras o via aceita", 8),
         ("camera compativel", 8), ("cameras compativeis", 8), ("compatibilidade", 7), ("funciona com", 5),
         ("posso usar minha camera", 8), ("preciso comprar camera", 8), ("camera ip", 6), ("camera rtsp", 7), ("rtsp", 5),
         ("hls", 5), ("webcam", 5), ("camera de celular", 7), ("camera existente", 7), ("cameras ja instaladas", 8),
         ("requisitos da camera", 8), ("qualidade da camera", 7), ("resolucao", 5), ("iluminacao", 5), ("angulo", 5),
         ("onde posicionar", 7), ("qual camera devo", 8), ("qual camera usar", 8)],
        "O VIA aproveita câmeras que você já tem, desde que consigam enviar vídeo por um stream de rede (HLS, MJPEG ou similar; RTSP precisa de um "
        "gateway que converta para HLS/WebRTC) ou, para testes, a webcam do navegador.\n\n"
        "Para uma boa detecção, a imagem deve mostrar a via com clareza: ângulo que enquadre a pista (de preferência elevado), boa iluminação, "
        "resolução de pelo menos 720p e câmera estável. Contas de clientes cadastram câmeras por URL pública.\n\n"
        "Se não tiver certeza de que a sua serve, abra um chamado com o modelo e a equipe avalia a compatibilidade.",
        ["Como cadastro uma câmera?"],
    ),
    Article(
        "dispositivos", "Uso no celular e no computador",
        [("no celular", 7), ("tem app", 7), ("aplicativo", 6), ("app para celular", 8), ("instalar", 5), ("baixar o app", 8),
         ("funciona no celular", 8), ("tablet", 5), ("navegador", 4.5), ("android", 6), ("iphone", 6), ("pwa", 6)],
        "O VIA é um app web: não precisa instalar nada. Abra no navegador do computador, tablet ou celular e entre com seu e-mail e senha; a "
        "interface se adapta à tela. No computador há ainda o popup do assistente, que você pode arrastar; no celular e no tablet, o botão do "
        "assistente abre a aba VIA.",
    ),
    Article(
        "retencao", "Quanto tempo os dados ficam",
        [("quanto tempo ficam", 8), ("por quanto tempo", 7), ("retencao", 7), ("historico de dados", 7), ("dados antigos", 7),
         ("dados de meses atras", 7), ("quanto tempo guarda", 8), ("prazo de armazenamento", 8), ("excluir dados antigos", 7)],
        "O histórico agregado (contagens, horários e ocorrências) fica salvo enquanto a sua conta existir, e você pode consultá-lo por qualquer "
        "período em Relatórios e com o assistente. Se precisar de uma política específica de retenção ou de exclusão, abra um chamado.",
    ),
    Article(
        "exportar_outros", "Exportar para planilha, API e integrações",
        [("excel", 8), ("csv", 8), ("planilha", 8), ("exportar dados", 7), ("baixar dados", 7), ("api", 5), ("integrar", 6),
         ("integracao", 6), ("power bi", 8), ("dados brutos", 8)],
        "Hoje a exportação é em PDF, em Relatórios (com todo o detalhamento). Exportação em planilha (CSV/Excel), API e integração com outras "
        "ferramentas ainda não estão disponíveis. Se você precisa disso, registre um chamado em Ajuda e privacidade: o seu pedido ajuda a priorizar.",
    ),
    Article(
        "lentidao", "Painel ou câmera lentos",
        [("lento", 6), ("lenta", 6), ("demora", 6), ("travando", 6), ("travou", 6), ("esta pesado", 6), ("muito devagar", 7)],
        "Se o painel ou a câmera estiverem lentos: confira a sua conexão com a internet (o vídeo depende da banda da câmera até o servidor); feche abas "
        "pesadas; no celular prefira Wi-Fi. Se persistir, abra um chamado informando o horário, o dispositivo e o que estava fazendo.",
    ),
    Article(
        "excluir_camera", "Como excluir uma câmera",
        [("excluir camera", 8), ("excluir uma camera", 8), ("remover camera", 8), ("remover uma camera", 8), ("apagar camera", 8),
         ("deletar camera", 8), ("tirar camera", 7), ("desativar camera", 7), ("retirar camera", 7)],
        "Para excluir uma câmera: abra o pino dela no mapa (Visão geral) e use Excluir câmera, ou localize-a na lista “Câmeras sem endereço no mapa”. "
        "Ela deixa de ser monitorada e some do mapa; o histórico já registrado permanece nos relatórios. Excluir libera a vaga no limite de câmeras do plano.",
    ),
    Article(
        "comparar_periodos", "Como comparar períodos",
        [("como comparo", 8), ("como comparar", 8), ("comparar periodos", 7), ("posso comparar", 7), ("da para comparar", 8)],
        "Pergunte ao assistente, por exemplo: “Compare 8h às 10h com 14h às 16h ontem”. No relatório em PDF, a comparação com o período anterior "
        "aparece automaticamente quando há dados comparáveis (o mesmo número de dias com leitura).",
    ),
]
