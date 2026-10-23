# CLAUDE.md

Guia para quem (pessoa ou agente) for mexer neste projeto: um app GTK4/libadwaita em Python que
substitui o software oficial de Windows dos teclados KBM! GAMING TG600/TG700 (USB `4a4c:e987`).
O protocolo foi obtido por engenharia reversa e está documentado em `docs/PROTOCOL.md`.

## Comandos

```bash
python3 -m kbm_tg700                         # roda o app a partir do código
python3 -m unittest discover -s tests -v     # testes (não precisam do teclado)
pyflakes3 kbm_tg700 tests tools              # lint usado no CI (apt install pyflakes3)
./build-deb.sh                               # gera dist/kbm-tg700_<versão>_all.deb
python3 tools/factory_reset.py               # recupera o teclado se algo for gravado errado
```

Para acessar o teclado sem root: `sudo cp packaging/70-kbm-tg700.rules /etc/udev/rules.d/`,
depois `sudo udevadm control --reload-rules && sudo udevadm trigger`.

## Estrutura

| Arquivo | Papel |
|---|---|
| `kbm_tg700/protocol.py` | Pacotes HID, classe `Device` (LED, macros, mapa de teclas, reset) |
| `kbm_tg700/keymap.py` + `layouts.json` | Layouts por modelo e montagem do mapa de 132 posições |
| `kbm_tg700/hidinput.py` | Leitura dos relatórios de teclado para a aba "Testar teclas" |
| `kbm_tg700/hidcodes.py` | Nomes de HID usages e tradução evdev → HID (gravação de macro) |
| `kbm_tg700/profile.py` | Perfil do usuário em `~/.config/kbm-tg700/profile.json` |
| `kbm_tg700/app.py` | Interface: uma janela com abas Iluminação, Macros, Teclas, Testar teclas |
| `tools/` | Scripts de diagnóstico interativos usados com o teclado real |
| `packaging/` | Regra udev, `.desktop` e ícone SVG (também usado no README) |

## Pontos que não são óbvios

- **Enum × opcode.** As constantes `CMD_*` são o enum interno do app original, não o byte enviado.
  `opcode()` faz a tradução (ex.: `CMD_KEYBOARD_LED = 0x06` vira o opcode `0x07`). Use sempre
  `Device.build`/`Device.command`, nunca monte o byte 1 na mão.
- **Gravar o mapa de teclas regrava as 132 posições.** Não existe comando de leitura do mapa, então
  `write_keymap` escreve todas as teclas a partir de `layouts.json`. Um código errado no layout quebra
  aquela tecla para todo mundo. Foi o caso do `/?` do TG700: o arquivo do fabricante dizia `0x38`
  (`;:` no ABNT2), o certo é `0x87`. Valide mudanças de layout na aba "Testar teclas".
- **Só a camada 0 (normal) é gravada.** A camada Fn existe (`[2]` = camada), mas os valores de fábrica
  dela são desconhecidos; gravá-la sem conhecê-los apaga as funções de Fn.
- **A tecla Fn não envia nada ao computador.** Ela é resolvida no firmware (entrada `[1,0,0,0]`).
- **Macros:** buffer fixo de 248 bytes em 5 pacotes, no máximo 62 eventos de 4 bytes e 10 slots.
- **Nomes de modos e direções** em `MODE_NAMES` e `DIRECTIONS` foram identificados olhando o teclado
  real; os IDs `0x10` e `0x08` não têm nome no app original.
- **Interfaces USB:** só a interface vendor (usage page `0xFF1B`) aceita comandos; `find_hidraw`
  a localiza pelo descritor. As outras duas são lidas apenas pelo testador de teclas.

## Regras do projeto

- **Nunca adicione arquivos do software original** (executáveis, DLLs, imagens, recursos extraídos).
  O `.gitignore` bloqueia `*.exe` e `*.dll`. Descobertas novas entram em `docs/PROTOCOL.md`, escritas
  com suas palavras.
- Comandos novos do protocolo precisam ser testados no teclado real; não há emulador. Gravações
  podem deixar teclas erradas até um reset de fábrica, então avise o usuário antes de testar.
- Toda mudança em `protocol.py` ou `keymap.py` deve vir com teste em `tests/` conferindo os bytes
  exatos (use o `FakeDevice` de `tests/test_protocol.py`).
- Interface e documentação em português do Brasil. Código, nomes e comentários em inglês.
- Sem dependências de pip: só a biblioteca padrão + PyGObject (GTK 4, libadwaita ≥ 1.4), que vêm do
  apt no Ubuntu 24.04. O `.deb` é `Architecture: all` e roda o código direto de `/usr/lib/kbm-tg700`.

## Release

1. Atualize `__version__` em `kbm_tg700/__init__.py` e adicione a seção no `CHANGELOG.md`.
2. Commit, depois `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin main vX.Y.Z`.
3. `.github/workflows/release.yml` confere se a tag bate com a versão, roda os testes e publica a
   Release com o `.deb` e as notas do CHANGELOG.
