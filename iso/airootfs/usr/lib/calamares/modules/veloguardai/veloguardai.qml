/* VeloGuardOS — Calamares AI setup page (original).
 * Lets the installer pick a cloud AI (OpenAI / Anthropic) with API key + model,
 * or "Local host" → choose an Ollama model to install. Choices are written to
 * Calamares global storage and applied by the veloguardaijob module.
 *
 * NOTE: first cut — the Calamares QML/global-storage API is version-specific
 * (3.3 / Qt6). This needs a boot test of the live ISO to validate + tune.
 */
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: page
    width: 800; height: 480

    function gset(k, v) { try { Global.setValue(k, v) } catch (e) {} }

    StackLayout {
        id: stack
        anchors.fill: parent
        anchors.margins: 24
        currentIndex: 0

        // ---- View 0: cloud AI (API) -------------------------------------
        ColumnLayout {
            spacing: 14
            Label { text: "AI setup"; font.pixelSize: 22; font.bold: true; color: "#13203a" }
            Label {
                text: "VeloGuardOS is AI-first. Pick a cloud provider and key, or host it locally."
                wrapMode: Text.WordWrap; Layout.fillWidth: true; opacity: 0.8
            }

            RowLayout {
                spacing: 10; Layout.fillWidth: true
                Label { text: "Provider:" }
                ComboBox {
                    id: provider
                    Layout.preferredWidth: 220
                    model: ["OpenAI API", "Anthropic"]
                    onCurrentTextChanged:
                        gset("veloguard_ai_provider", currentIndex === 1 ? "anthropic" : "openai")
                    Component.onCompleted: gset("veloguard_ai_provider", "openai")
                }
            }

            Label { text: "API key:" }
            TextField {
                id: apiKey
                Layout.fillWidth: true
                echoMode: TextInput.Password
                placeholderText: "paste your API key (stored locally, chmod 600)"
                onTextChanged: gset("veloguard_ai_key", text)
            }

            Label { text: "Default model:" }
            TextField {
                id: model
                Layout.fillWidth: true
                placeholderText: provider.currentIndex === 1 ? "claude-haiku-4-5" : "gpt-4o-mini"
                onTextChanged: gset("veloguard_ai_model", text)
            }

            Item { Layout.fillHeight: true } // spacer pushes the button to the bottom

            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }   // push to bottom-right
                Button {
                    text: "Local host  ▸"
                    onClicked: { gset("veloguard_ai_provider", "ollama"); stack.currentIndex = 1 }
                }
            }
        }

        // ---- View 1: local (Ollama) model picker ------------------------
        ColumnLayout {
            spacing: 14
            Label { text: "Local AI (Ollama)"; font.pixelSize: 22; font.bold: true; color: "#13203a" }
            Label {
                text: "Choose a model to install locally — private, free, runs on this machine."
                wrapMode: Text.WordWrap; Layout.fillWidth: true; opacity: 0.8
            }

            ListView {
                id: models
                Layout.fillWidth: true; Layout.fillHeight: true
                clip: true
                model: ListModel {
                    ListElement { name: "llama3.2:3b   (small, fast — recommended)" ; id_: "llama3.2:3b" }
                    ListElement { name: "llama3.1:8b   (balanced)"                  ; id_: "llama3.1:8b" }
                    ListElement { name: "qwen2.5:7b    (strong, general)"           ; id_: "qwen2.5:7b" }
                    ListElement { name: "qwen2.5:14b   (needs a capable GPU)"       ; id_: "qwen2.5:14b" }
                    ListElement { name: "llama3.1:70b  (high-end — the bonus tier)" ; id_: "llama3.1:70b" }
                }
                delegate: RadioDelegate {
                    width: ListView.view.width
                    text: name
                    checked: models.currentIndex === index
                    onClicked: { models.currentIndex = index; gset("veloguard_ai_model", id_) }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Button { text: "◂  Back to cloud"; onClicked: { gset("veloguard_ai_provider", "openai"); stack.currentIndex = 0 } }
                Item { Layout.fillWidth: true }
            }
        }
    }
}
