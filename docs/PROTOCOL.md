# Protocolo USB do KBM! GAMING TG600 / TG700

Documentação do protocolo de configuração, obtida por engenharia reversa para fins de
interoperabilidade (permitir usar o teclado no Linux). Nenhum código do software original é
redistribuído neste projeto.

## Origem

O software oficial para Windows (`KGTG600 - KGTG700 - Software.exe`) é um instalador Inno Setup 5.5.7
contendo um app Qt5 (`TECLADO MECANICO GAMER.exe`) e uma biblioteca de comunicação (`witmodSdk.dll`).
O protocolo foi entendido a partir:

- da tabela de exportações e do código desmontado da `witmodSdk.dll` (`CWitmodHid_HidWriteBuff` etc.);
- das funções do executável que montam cada pacote (identificadas pelas mensagens de log ao lado de
  cada uma, ex.: `USB serial port [Write keyboard Led] ...`);
- dos arquivos de layout embutidos nos recursos Qt (`KeyInfo_*.config`);
- de testes com o teclado real.

## Dispositivo

| Campo | Valor |
|---|---|
| VID:PID | `4a4c:e987` (também `e988` dongle, `e989`) |
| Chip | JieLi |
| Modelos | TG700 = `MK69_JLRGB` (68 teclas), TG600 = `JLMK60V2RGB`, TG600W = `JLEZ63BTRGB` |

Interfaces USB:

| Interface | Uso |
|---|---|
| 0 | Teclado boot (relatório de 8 bytes) |
| 1 | Report IDs: 2 mouse, 3 consumer, 4 system, 5 bitmap NKRO de usages `0x00..0x9F` |
| 2 | **Vendor**: usage page `0xFF1B`, usage `0x91`, report ID 1, 63 bytes de entrada/saída |

## Formato do pacote (interface 2)

64 bytes, escritos com `write()` no hidraw:

| Byte | Conteúdo |
|---|---|
| 0 | Report ID `0x01` |
| 1 | Opcode |
| 2 | Subcomando: `0x01` = consulta; ou camada / slot de macro |
| 3 | `0x00` |
| 4 | Índice do pacote (transferências em várias partes) |
| 5 | Tamanho dos dados |
| 6..61 | Dados |
| 62..63 | 16 bits baixos de um timestamp em ms (big endian), usado como nonce |

O app original usa um enum interno que a DLL traduz para o opcode:
`0..27 → 0x01..0x1C`, `28..37 → 0x40..0x49`, `38..44 → 0x1E..0x24`.
A resposta vem pela mesma interface com o mesmo opcode no byte 1.

## Comandos

| Função | Opcode | Detalhes |
|---|---|---|
| Handshake | `0x01` | dados `01` |
| LED do teclado | `0x07` | `[2]=1` consulta; escrita com 14 bytes (abaixo) |
| LED lateral | `0x08` | não existe no TG700 |
| LED por tecla | `0x09` | modo "Personalizado" (não implementado) |
| Lista de modos | `0x0A` | `[2]=1`; IDs dos modos até o marcador `A5 5A`, depois brilho máx. e velocidade máx. |
| Reset / dormir | `0x14` | `[2]=0` + dados `01` = reset de fábrica; `[2]=1` define e `[2]=2` consulta o tempo de dormir |
| Número de série | `0x15` | `[2]=1`, ASCII |
| Mapa de teclas | `0x18` | ver abaixo |
| Macro | `0x19` | ver abaixo |

### LED do teclado (14 bytes)

| Byte | Campo |
|---|---|
| 0 | Modo (ID da lista) |
| 1 | Brilho 0–4 |
| 2 | Velocidade 0–4 |
| 3–5 | Cor R, G, B |
| 6–8 | Cor de fundo R, G, B |
| 9 | Direção: 0 horário, 1 anti-horário, 2 esquerda, 3 direita, 4 baixo, 5 cima |
| 10 | Tipo de cor: bit 0 = arco-íris ("Full color") |
| 11 | Update |
| 12–13 | reservado |

IDs de modo na ordem informada pelo TG700: `02` Estático, `01` Respiração, `03` Cintilar,
`09` Ondulação automática, `04` Estrias, `00` Aurora, `0E` Ondulação, `0F` Reativo,
`06` Fogos de artifício, `07` Resposta rápida, `0B` Ritmo musical, `0C` Personalizado,
`10` e `08` (sem nome no app original).

### Mapa de teclas (`0x18`)

- Matriz de 6 linhas × 22 colunas = 132 posições, linha a linha (mesma ordem dos `KeyInfo_*.config`).
- 14 posições por pacote, 4 bytes cada: `[2]` = camada (0 = normal), `[4]` = nº do pacote (0–9).
- Entradas conhecidas:

| Entrada | Significado |
|---|---|
| `00 uu 00 00` | tecla com HID usage `uu` |
| `01 00 00 00` | Fn |
| `10 ss 00 00` | macro no slot `ss` |
| `00 00 00 00` | sem função |

Outros tipos vistos no código original e ainda não implementados: `0x11` mouse, `0x13` combinação
de teclas, `0x14`, `0x17` teclas avançadas (DKS).

### Macro (`0x19`)

- `[2]` = slot 0–9. Buffer fixo de 248 bytes enviado em 5 pacotes de 50+58+58+58+24 bytes.
- Pacote 0 começa com um cabeçalho de 8 bytes: `00, modo-1, 00, nº_eventos*4, 00, repetições, 00, 00`.
- Até 62 eventos de 4 bytes: `código, (apertar<<4) | mouse, atraso_hi, atraso_lo` (atraso em ms).
- Mouse: `1` esquerdo, `2` direito, `4` meio.

## Observações

O `KeyInfo_MK69_JLRGB.config` original traz a tecla `/?` (à esquerda do Shift direito) com o
código `0x38`, que no ABNT2 é `;:`. Este projeto usa `0x87`, igual ao layout do TG600.
