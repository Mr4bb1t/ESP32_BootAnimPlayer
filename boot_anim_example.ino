#include <SPI.h>
#include <TFT_eSPI.h>
#include <SPIFFS.h>
#include "boot_anim_player.h"

TFT_eSPI tft = TFT_eSPI();
BootAnimPlayer player;

void setup() {
    Serial.begin(115200);
    tft.init();
    tft.setRotation(0);
    tft.fillScreen(0);

    if (!SPIFFS.begin(true)) {
        Serial.println("SPIFFS failed!");
        return;
    }

    if (!player.begin("/boot_anim.bin")) {
        Serial.println("Anim load failed!");
        return;
    }

    Serial.printf("Anim: %dx%d, %dfps, %d frames\n",
        player.getWidth(), player.getHeight(),
        player.getFps(), player.getTotalFrames());

    uint16_t* buf = (uint16_t*)malloc(128 * 160 * 2);
    if (!buf) return;

    uint32_t interval = player.getFrameIntervalMs();
    uint32_t lastFrame = 0;

    while (player.decodeNextFrame(buf)) {
        while (millis() - lastFrame < interval) { yield(); }
        lastFrame = millis();
        tft.pushImage(0, 0, 128, 160, buf);
    }

    free(buf);
    player.end();
    SPIFFS.end();

    // Continue boot...
    tft.fillScreen(0);
}

void loop() {}
