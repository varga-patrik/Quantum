#include <iostream>       
#include <raylib.h>
#include <ctime>
#include <vector>
#include <sstream>
#include <filesystem>
#include <map>
#include "Correlator.h"

unsigned int windowHeight = 1080;
unsigned int windowWidth = 1920;

// Global UI settings:
const int uiElementWidth = 300;
const int uiElementHeight = 30;
const int uiTextSize = 20;

Font font;

std::vector<std::string> getBinFiles(const std::string& directoryPath) {
    std::vector<std::string> binFiles;

    for (const auto& entry : std::filesystem::directory_iterator(directoryPath)) {
        if (entry.is_regular_file() && entry.path().extension() == ".bin") {
            binFiles.push_back(entry.path().filename().string());
        }
    }

    return binFiles;
}

enum UiType { BUTTON, TEXTBOX, COMBOBOX};

typedef struct UIElement {
    int x;
    int y;
    int length;
    int height;
    int id;
    UiType type;
    std::string text;

    UIElement(int x, int y, int length, int height, int id, UiType type, std::string text)
        : x(x), y(y), length(length), height(height), id(id), type(type), text(text) {}
} UIElement;

class UIHandler {
public:
    std::vector<UIElement> elements;
    std::map<int, int> comboScrollIndex;
    int activeTextbox;
    Texture2D plotTexture;
    bool plotLoaded;

    UIHandler() {
        elements.push_back(UIElement(50, 100, uiElementWidth / 2, uiElementHeight, 0, UiType::BUTTON, "None"));
        elements.push_back(UIElement(200, 100, uiElementWidth / 2, uiElementHeight, 1, UiType::BUTTON, "Run"));
        elements.push_back(UIElement(50, 200, uiElementWidth, uiElementHeight, 2, UiType::TEXTBOX, "500"));
        elements.push_back(UIElement(50, 250, uiElementWidth, uiElementHeight, 3, UiType::COMBOBOX, "First input file"));
        elements.push_back(UIElement(50, 450, uiElementWidth, uiElementHeight, 4, UiType::COMBOBOX, "First input file"));
        elements.push_back(UIElement(50, 650, uiElementWidth, uiElementHeight, 5, UiType::COMBOBOX, "First input file"));
        elements.push_back(UIElement(50, 850, uiElementWidth, uiElementHeight, 6, UiType::COMBOBOX, "First input file"));
        elements.push_back(UIElement(400, 250, uiElementWidth, uiElementHeight, 7, UiType::COMBOBOX, "Second input file"));
        elements.push_back(UIElement(400, 450, uiElementWidth, uiElementHeight, 8, UiType::COMBOBOX, "Second input file"));
        elements.push_back(UIElement(400, 650, uiElementWidth, uiElementHeight, 9, UiType::COMBOBOX, "Second input file"));
        elements.push_back(UIElement(400, 850, uiElementWidth, uiElementHeight, 10, UiType::COMBOBOX, "Second input file"));
        activeTextbox = -1;
        plotLoaded = false;
    }

    void findElement(int mouseX, int mouseY) {
        for (int i = 0; i < elements.size(); i++) {
            UIElement& element = elements[i];

            if (element.type == UiType::COMBOBOX && element.id == activeTextbox) {
                std::vector<std::string> files = getBinFiles("rawdata");
                int scroll = comboScrollIndex[element.id];
                int visibleCount = 5;

                for (int j = 0; j < visibleCount && scroll + j < files.size(); j++) {
                    int drawY = element.y + (j + 1) * element.height;
                    if (mouseX >= element.x && mouseX <= element.x + element.length &&
                        mouseY >= drawY && mouseY <= drawY + element.height) {
                        element.text = "rawdata/" + files[scroll + j];
                        activeTextbox = -1;
                        return;
                    }
                }
            }

            if (mouseX >= element.x && mouseX <= element.x + element.length &&
                mouseY >= element.y && mouseY <= element.y + element.height) {
                elementPressed(element);
                return;
            }
        }
        activeTextbox = -1; // clicked outside any element
    }

    std::string getElementText(int id) {
        for (int i = 0; i < elements.size(); i++) {
            UIElement& element = elements[i];
            if (element.id == id) {
                return element.text;
            }
        }
        return std::string("");
    }

    void elementPressed(UIElement& element) {
        if (element.type == UiType::BUTTON) {
            switch (element.id) {
            case 0:
                if (element.text == "None") {
                    element.text = "Bound";
                }
                else if (element.text == "Bound") {
                    element.text = "None";
                }
                break;

            case 1: {
                Correlator corr(/*chunkSize*/ 100000, /*N*/ (1ULL << 16));

                uint64_t tau = std::strtoull(getElementText(2).c_str(), nullptr, 10);

                bool reduc = (getElementText(0) != "None");

                std::vector<std::string> dataset1;
                std::vector<std::string> dataset2;
                dataset1.push_back(getElementText(3));
                dataset1.push_back(getElementText(4));
                dataset1.push_back(getElementText(5));
                dataset1.push_back(getElementText(6));
                dataset2.push_back(getElementText(7));
                //dataset2.push_back(getElementText(8));
                //dataset2.push_back(getElementText(9));
                //dataset2.push_back(getElementText(10));

                int ret = corr.runCorrelation(reduc, dataset1, dataset2, tau);

                reloadPlot();
                break;
            }
            default:
                break;
            }
        }
        else {
            activeTextbox = element.id;
        }
    }

    void handleTextInput() {
        if (activeTextbox == -1) return;

        for (int i = 0; i < elements.size(); i++) {
            if (elements[i].id == activeTextbox && elements[i].type == UiType::TEXTBOX) {
                if (IsKeyPressed(KEY_ENTER)) {
                    activeTextbox = -1;
                    return;
                }
                if (IsKeyPressed(KEY_BACKSPACE)) {
                    if (!elements[i].text.empty()) {
                        elements[i].text.pop_back();
                    }
                }
                int key = GetCharPressed();
                while (key > 0) {
                    elements[i].text.push_back((char)key);
                    key = GetCharPressed();
                }
                return;
            }
        }
    }

    void drawElements() {
        for (int i = 0; i < elements.size(); i++) {
            UIElement& e = elements[i];
            DrawRectangleLines(e.x, e.y, e.length, e.height, LIGHTGRAY);
            DrawTextEx(font, e.text.c_str(), { (float)e.x + 5, (float)e.y + 5 }, uiTextSize, 1, BLACK);

            if (e.type == UiType::TEXTBOX && e.id == activeTextbox) {
                DrawRectangleLines(e.x, e.y, e.length, e.height, RED);
            }
            else if (e.type == UiType::COMBOBOX && e.id == activeTextbox) {
                std::vector<std::string> files = getBinFiles("rawdata");
                int scroll = comboScrollIndex[e.id];
                int visibleCount = 5;

                if (scroll < 0) scroll = 0;
                if (scroll > (int)files.size() - visibleCount) scroll = std::max(0, (int)files.size() - visibleCount);
                comboScrollIndex[e.id] = scroll;

                for (int j = 0; j < visibleCount && scroll + j < files.size(); j++) {
                    int drawY = e.y + (j + 1) * e.height;
                    DrawRectangleLines(e.x, drawY, e.length, e.height, LIGHTGRAY);
                    DrawTextEx(font, files[scroll + j].c_str(), { (float)e.x + 5, (float)drawY + 5 }, uiTextSize, 1, BLACK);
                }
            }
        }
        if (plotLoaded) { 
            DrawTexture(plotTexture, 400, 75, WHITE);
        }
    }

    void reloadPlot() {
        system("gnuplot -e \"set terminal pngcairo size 1300,800; set output 'output.png'; plot 'a.dat' using 1 with lines, 'a.dat' using 2 with lines\"");

        // Reload the texture
        if (plotLoaded) {
            UnloadTexture(plotTexture);
        }
        plotTexture = LoadTexture("output.png");
        plotLoaded = true;
    }
};

UIHandler handler;

void inputHandler() {
    if (IsMouseButtonPressed(MOUSE_BUTTON_LEFT)) {
        handler.findElement(GetMouseX(), GetMouseY());
    }

    if (handler.activeTextbox != -1) {
        for (auto& e : handler.elements) {
            if (e.id == handler.activeTextbox && e.type == UiType::COMBOBOX) {
                float scroll = GetMouseWheelMove();
                handler.comboScrollIndex[e.id] -= (int)scroll;
            }
        }
    }

    handler.handleTextInput();
}

int main() {
    InitWindow(windowWidth, windowHeight, "Correlator App");
    font = LoadFont("C:/Windows/Fonts/tahoma.ttf");
    SetTargetFPS(60);

    while (!WindowShouldClose()) {
        inputHandler();

        BeginDrawing();
        ClearBackground(WHITE);
        handler.drawElements();
        EndDrawing();
    }
    UnloadFont(font);
    CloseWindow();
    return 0;
}
