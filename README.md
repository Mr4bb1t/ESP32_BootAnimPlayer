# R4bb1t FHC - Boot Animation Framework

Este diretório contém o framework completo para criação, conversão e reprodução de vídeos/animações comprimidas diretamente na tela de microcontroladores ESP32, projetado inicialmente para displays ST7735/ST7789 via SPI, sem necessidade de módulos de cartão SD.

## Arquitetura Técnica

Rodar vídeos brutos no ESP32 geralmente causa travamentos (*stack overflow* e esgotamento de *heap*) por falta de memória ou exige leitura de arquivos enormes. Para solucionar isso, desenvolvemos este sistema híbrido que funciona da seguinte maneira:

1. **Codificação Dinâmica (Python):** O conversor Python (`video_to_bin.py`) decodifica o vídeo original usando o engine do OpenCV. Ele extrai os frames, aplica redimensionamento com interpolação otimizada, converte a cor de 24-bits (RGB888) para 16-bits (RGB565 *Big-Endian*, otimizado para barramento SPI do display) e aplica um algoritmo de sub-amostragem para forçar a taxa de FPS desejada.
2. **Compressão ZLIB & Decimação Inteligente (Python):** O buffer gigante contendo os frames brutos é submetido à compressão ZLIB de nível 9. O resultado é encapsulado com um cabeçalho customizado (`R4BT`) de 20 bytes contendo os metadados vitais de resolução e taxa de quadros. Se você configurar um limite de KB (ex: 800 KB) e o arquivo final ficar maior que isso, o algoritmo intercala ativamente o descarte de frames em loops, otimizando o tamanho sem perder a continuidade (drop-frame inteligente).
3. **Decodificação de Hardware (ESP32):** No firmware C++, utilizamos a classe `BootAnimPlayer`. Ela lê os dados comprimidos armazenados na partição SPIFFS e utiliza a biblioteca acelerada em ROM (`rom/miniz.h`), que já vem embutida no silício do ESP32, para descomprimir os dados em velocidade nativa C.
4. **FIFO Streaming:** Em vez de tentar carregar o arquivo todo na RAM (o que seria impossível), a classe aloca um buffer estático rotativo e um dicionário de descompressão. O descompressor Miniz processa blocos dinamicamente à medida que são lidos do flash (SPIFFS) e manda imediatamente para a VRAM do display ST7735 usando `pushImage()`. O resultado é um playback sedoso com baixíssimo custo de memória.

## Como gerar e testar sua própria animação?

Você precisará do Python instalado na sua máquina.

### 1. Instale as dependências
```bash
pip install opencv-python numpy
```

### 2. Execute o Conversor
O nosso conversor possui uma **Interface Gráfica (GUI)** amigável! Basta rodar o script sem nenhum argumento para abrir a tela:

```bash
python video_to_bin.py
```

Pela interface você poderá:
* Selecionar o seu vídeo (`.mp4`, `.gif`, `.avi`, etc).
* Escolher as dimensões exatas de saída (ex: `128x160` para R4bb1t, ou maiores para outros displays).
* Determinar a taxa de FPS (ex: `16` ou `24`).
* Cortar trechos indesejados definindo o `Segundo Inicial` e a `Duração`.
* **Tamanho Máximo (Auto-Drop)**: Limite o peso em KB. Se o vídeo exceder, ele descarta inteligentemente os quadros para espremer o arquivo no limite do seu ESP32.
* Ver os frames rodando e sendo filtrados ao vivo durante o processamento.
* Usar o **Player Embutido**, que permite visualizar no próprio computador o `.BIN` resultante pra ver como ele se comportará no hardware.

### 3. Modo Linha de Comando (CLI Avançado)
Se você preferir rodar via automação, basta passar os parâmetros no terminal:

```bash
python video_to_bin.py meu_video.mp4 boot_anim.bin --width 128 --height 160 --fps 24 --max_kb 900
```
*(Para testar apenas o visualizador via CLI, passe o comando `python video_to_bin.py meu_anim.bin none --play`)*

### 4. Faça o Upload
Após gerar o arquivo `boot_anim.bin`, coloque-o na pasta `data` na raiz do seu projeto C++ e faça o upload da partição SPIFFS via PlatformIO:
> **PlatformIO > Project Tasks > (seu_ambiente) > Platform > Upload Filesystem Image**

### Considerações Importantes sobre Armazenamento
O ESP32 tradicional possui 4MB de memória Flash. Um particionamento padrão reserva menos de 1MB para o SPIFFS. Se o seu vídeo for muito longo, a compressão ZLIB pode não ser suficiente.
**Recomendação:** Para usar animações ricas, altere o particionamento no seu `platformio.ini` para liberar mais SPIFFS (ex: usando `no_ota.csv` para garantir 2MB de armazenamento de sistema de arquivos).
