import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation
    Timer { interval: 6000; running: true; repeat: true; onTriggered: presentation.goToNextSlide() }

    Slide {
        Rectangle { anchors.fill: parent; color: "#13203a" }
        Text {
            anchors.centerIn: parent; width: parent.width * 0.8
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            color: "#e8eef7"; font.pixelSize: 24
            text: "VeloGuardOS — AI-first, and guarded.\nThe AI can run the machine; the guard keeps you in control."
        }
    }
    Slide {
        Rectangle { anchors.fill: parent; color: "#13203a" }
        Text {
            anchors.centerIn: parent; width: parent.width * 0.8
            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
            color: "#17a2b8"; font.pixelSize: 24
            text: "Auto-VPN on untrusted Wi-Fi · honeypot + AI diagnosis · app sandbox · signed updates."
        }
    }
}
