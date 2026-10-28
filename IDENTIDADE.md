# Identidade visual

O que o Companheiro de inglês parece, por quê, e como manter isso quando uma tela nova aparece.
Antes de mexer no visual, leia o conceito e a seção "Assim sim, assim não". O resto é consulta.

## O conceito: caderno de campo da fala

Quem usa o app é o pesquisador de campo da própria voz. Grava, mede som a som, anota o que saiu
diferente, volta no dia certo para conferir. O app é o caderno dessa pesquisa: sóbrio, legível,
com as marcas de quem trabalha com mapas e medidas, e com a natureza do Brasil nas cores.

Tudo o que aparece na tela deve passar por este teste: **isto é uma anotação de campo sobre a
fala, ou é enfeite?** Enfeite sai.

Três ideias sustentam o resto:

- **Medida, não opinião.** O app mostra o que ouviu: a onda, o espectro, a taxa comparada com a
  dos nativos. Os desenhos de fundo são instrumentos de laboratório, não ilustrações.
- **Mapa.** O progresso é um terreno que vai sendo levantado: curvas de nível, cotas, o relevo
  dos seus sons. Daí as curvas, as barras com a linha dos nativos e o Progresso por sessão.
- **Mata Atlântica.** As cores têm nome de coisa daqui: névoa, folha, jenipapo, mata, pitaya,
  ipê. Nada de azul de software nem de laranja de startup.

## O nome

**Companheiro de inglês**, assim, com "de inglês" em minúsculas. Curto, quando não cabe:
**Inglês** (é o nome no ícone do celular). Nunca "Companheiro", sozinho, nem sigla.

Em texto corrido, o app fala de si como "o app". O tutor da conversa é "o tutor". A IA de dúvidas
é "o Perguntar", nunca "o tutor" (são duas coisas).

## A marca: θ com a voz

O θ é o som mais difícil para quem fala português, e o símbolo que mais aparece no app. Na marca,
a barra do meio do θ vira a onda de uma voz: o som e a medida dele num traço só.

```
   ╭──────╮
  │        │
  │ ─∿∿─  │      θ: a elipse alta; a barra é uma onda curta: sobe, desce e sobe de novo
  │        │
   ╰──────╯
```

- **Construção** (`static/img/marca.svg`): elipse de 54 × 76 num quadro de 100, traço de 8, pontas
  redondas. A onda ocupa o meio: reta nas pontas e, no centro, dois picos e um vale (y de 36 a
  64, picos a 10 de distância), dentro da elipse. Mais apertada que isso, o traço cola e vira
  mancha nos tamanhos grandes.
- **Traço** (`marca.svg`): só o contorno, na cor do contexto (`currentColor`). É a versão de
  dentro do app: menu, boas-vindas, impressos.
- **Selo** (`static/icon.svg`, `icon-180.png`, `icon-512.png`): a marca em folha sobre o verde
  mata, num quadrado de cantos redondos (raio 22 em 96). É o ícone do navegador e do celular.
- **Marca com nome:** o selo de 36 px e, ao lado, "Companheiro / de inglês" em duas linhas, na
  Atkinson 600. É o cabeçalho do menu. O nome nunca vai em Gentium (a Gentium é das frases em
  inglês e do IPA, não do nome).
- **Tamanho mínimo:** 16 px (favicon). Nesse tamanho a onda vira uma barra grossa, e tudo bem:
  ainda é um θ.
- **Espaço livre:** em volta do selo, pelo menos a largura da sua barra (8 em 100).
- **Não:** não colorir a onda de outra cor, não inclinar, não pôr sombra, não trocar o θ por
  outra letra, não escrever o nome dentro do selo.

## Cores

Nome de coisa daqui. Cada cor tem um papel; a cor é informação, não decoração.

| Nome | Claro | Escuro | Papel |
|---|---|---|---|
| névoa | `#ECF0EC` | `#121A22` | o fundo da tela |
| folha | `#FAFBF8` | `#1A2530` | superfícies: painéis, menu, cartões |
| jenipapo | `#1B2A3A` | `#E6ECE8` | o texto (tinta) |
| mata | `#1F6B4F` | `#5FB98E` | a ação (o botão cheio, o link), o certo, a marca |
| pitaya | `#B23A64` | `#E2799D` | o que saiu diferente: som trocado, erro, nota "Errei" |
| ipê | `#E3B23C` | `#E9C25E` | atenção e foco: o sublinhado do som da vez, a dica, o que faltou |

Regras:

- **Uma cor de destaque por elemento.** O botão cheio é mata; o resto, contorno. O próximo passo
  de Hoje é o único botão cheio da lista.
- **Mata é "certo" e pitaya é "diferente".** Nunca o contrário, nunca verde para erro.
- **Mata e pitaya nunca são duas séries do mesmo gráfico** (quem não distingue verde de vermelho
  não separa as duas). Um gráfico, uma série; a referência dos nativos é uma linha na cor da tinta.
- **Os tons "wash"** (`--mata-wash`, `--pitaya-wash`, `--ipe-wash`) são fundo de estado: a opção
  escolhida, a palavra marcada, o passo da vez. Não são cor de texto.
- **Texto sempre em tinta** (`--ink`, `--ink-2`, `--ink-3`), nunca na cor da série. O `--ink-3`
  claro é `#5E6A75`, não mais claro: abaixo disso reprova em texto pequeno.
- **Escuro não é o claro invertido:** as cores escuras foram escolhidas uma a uma. Um tom novo
  precisa de versão para os dois temas, testada nos dois.

## Tipos

Dois tipos, com papéis que não se misturam:

- **Gentium Book Plus** (SIL): títulos, as frases em inglês, as palavras que você diz e o IPA.
  É a letra do "material de pesquisa": o que é inglês, o que é som. Tem o IPA inteiro.
- **Atkinson Hyperlegible Next**: tudo o que é interface em português: menu, botões, rótulos,
  explicações, legendas. Feita para ler sem esforço, com peso variável (200 a 800).

Escala: 17 px de base (16 no celular, 18 acima de 1800 px de tela, 19 acima de 2300). Degraus:
`--step--1` 0,81 rem, `--step-0` 1 rem, `--step-1` 1,25, `--step-2` 1,56, `--step-3` 2,1,
`--step-4` 2,9. A frase para falar (`.say`) cresce com a largura da coluna, de 1,8 a 3,2 rem.

- Linha de texto corrido com até ~68 caracteres. Largura a mais vira coluna, não linha comprida.
- **Caixa normal de frase.** Nada em CAIXA ALTA, nem rótulo, nem botão.
- Nenhuma palavra solta em itálico ou cor dentro de um título para "dar destaque".
- Itálico na Gentium só para a tradução ou o exemplo em inglês. Sublinhado `_x_` não existe
  nos textos do app: o sublinhado é lacuna de exercício.

## Os motivos

Os desenhos do app são instrumentos. Cada um tem um significado e um lugar; fora dele, não aparece.

| Motivo | O que é | Onde | Força |
|---|---|---|---|
| a onda da voz (`img/voz.svg`) | o traço de "I think three months is enough", uma rajada por palavra | no alto de cada página, acima do título | 11% (13% no escuro) |
| as curvas de nível (`img/relevo.svg`) | o relevo dos seus sons, como num mapa | fixas atrás de tudo, apagadas no meio da tela | 8,5% (10%) |
| o perfil da boca (`img/boca.svg`) | o corte de fonética, com a língua no θ | no pé do menu, onde nunca passa texto | 30% |
| o símbolo do som (`.focus-glyph`) | o IPA do som da vez, em Gentium | a peça grande de Hoje | tinta cheia, sublinhado ipê |

Regras:

- **Nada decorativo por baixo do texto.** Um desenho que a página rola por cima parece andar e
  atrapalha a leitura. Fica em zona sem conteúdo (o pé do menu, o alto da página) ou vira textura
  uniforme e quase invisível (as curvas).
- Todo motivo é máscara pintada com `--mata`: funciona nos dois temas sem segunda versão.
- Motivo novo só com significado novo. "Ficou bonito" não é significado.
- Com `prefers-contrast: more`, somem todos.

## Superfícies e espaço

- O fundo é névoa com um grão fino (papel), uma luz de mata no alto à esquerda e uma de ipê
  embaixo à direita, bem suaves. Sem grão, a cor chapada parecia crua.
- **A mesa de trabalho** (`.stage`): onde você fala. Folha, borda fina, raio 18, sombra curta. É
  o mesmo espaço em toda tela de exercício. Painéis comuns (`.panel`) têm raio 12; botões, 10;
  campos, 8; chips e o seletor de modo, redondos.
- **A bancada** (`.bench`): o exercício à esquerda e o apoio à direita (raio-x, fila, dica,
  tentativas), parado enquanto você rola. Uma coluna até 900 px de conteúdo, duas até 1480, três
  onde há o que pôr.
- Listas são listas, com fio entre os itens: sons, cenários e cartões não viram grade de cartões
  iguais. Número só onde há sequência de verdade (os passos de Hoje, os degraus da escada, a fila).
- O menu é levemente translúcido (deixa o grão passar); no celular vira barra de baixo, sólida.

## Dados

- Um gráfico, uma série. A linha dos nativos é a referência, na cor da tinta, com rótulo.
- Colunas finas com topo redondo de 4 px, linha de 2 px, ponto final com anel.
- Texto do gráfico sempre do mesmo tamanho (0,72 rem), desenhado na largura real do cartão.
- Toda medida vem com o seu "de quantas": "20 de 41 vezes", nunca só a porcentagem.
- Cada gráfico tem a tabela ("Ver os números").

## Texto

O texto é parte do desenho e segue as mesmas regras de economia.

- Português do Brasil, direto, em segunda pessoa ("você"). Sem tom de manual nem de propaganda.
- O botão diz o que acontece: "Começar", "Conferir", "Virar (espaço)", "Levar os cartões".
  O mesmo nome do começo ao fim: quem clica em "Conectar" vê "Conectado".
- Erro diz o que houve e o que fazer, sem pedir desculpa: "Não deu para julgar: leia a frase
  inteira, no ritmo normal, e grave de novo."
- Tela vazia é convite: o que fazer para ela encher, com o botão.
- O inglês aparece em Gentium; o português que explica, em Atkinson. A tradução, em itálico.
- Nomes das telas: Hoje, Conversar, Pronúncia, Fale certo, Cartões, Entender, Perguntar, Meus
  erros, Progresso, Histórico, Ajustes. Em maiúscula só a primeira letra.

## Assim sim, assim não

| Sim | Não |
|---|---|
| a frase em Gentium grande, o botão verde embaixo, a dica em ipê ao lado | três cartões iguais com ícone, título e sombra |
| o θ gigante de Hoje com o sublinhado ipê | banner com foto de pessoa sorrindo |
| "20 de 41 vezes (49%); nativos, 1%" | "Sua pronúncia está 49% boa!" |
| curvas de nível quase invisíveis atrás de tudo | símbolos soltos atrás da lista de passos |
| mata no botão cheio, o resto em contorno | dois botões cheios na mesma linha |
| "Não deu para julgar. Leia a frase inteira e grave de novo." | "Ops! Algo deu errado :(" |
| a lista de sons com símbolo, nome, barra e contagem | grade de cards de sons com gradiente |
| rótulo em caixa normal: "Som da vez" | SOM DA VEZ |

## Arquivos

| O quê | Onde |
|---|---|
| as cores, tipos e medidas (a fonte da verdade) | `static/css/app.css`, bloco `:root` e `[data-theme="dark"]` |
| a marca em traço | `static/img/marca.svg` (e o símbolo `#i-marca` em `static/index.html`) |
| o selo | `static/icon.svg`, `static/icon-180.png`, `static/icon-512.png` |
| os motivos | `static/img/voz.svg`, `relevo.svg`, `boca.svg` (gerados por scripts; o relevo por marching squares) |
| as fontes e licenças | `static/fonts/` |
| os ícones do menu | o sprite `<svg>` no começo de `static/index.html`: traço 1,7, pontas redondas, 24 × 24 |
