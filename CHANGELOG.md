# Changelog

## 1.1.2

- Corrige o remapeamento de teclas (e macros) voltando ao padrão depois de reiniciar o computador ou
  reconectar o teclado: o firmware guarda o mapa em memória volátil. Agora o perfil salvo é regravado
  automaticamente ao entrar na sessão e sempre que o teclado aparece (serviço de usuário, disparado
  também pela regra udev), sem precisar abrir o app. Também dá para rodar manualmente com `kbm-tg700 --restore`.

## 1.1.0

- Janela Sobre com autor, créditos, notas da versão, links e informações de depuração.
- O número de série do teclado não aparece mais na barra superior.
- Screenshots do app no README.

## 1.0.0

Primeira versão pública.

- Iluminação: modo, cor, arco-íris, brilho, velocidade e direção.
- Macros: até 10 macros com até 62 eventos (teclas e cliques de mouse), gravadas no teclado.
- Teclas: remapear, atribuir macro ou desativar.
- Aba **Testar teclas**, que lê os relatórios HID brutos do teclado.
- Restaurar padrão de fábrica.
- Pacote `.deb` com regra udev para acesso sem root.
