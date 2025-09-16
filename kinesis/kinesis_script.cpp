#include "KinesisUtil.h"

int main() {

    if (TLI_BuildDeviceList() == 0) {
        KinesisUtil device("55526814");
        device.activate();
        device.startPolling(200);
        device.load();
        device.clear();
        device.home();
        device.wait_for_command(2, 0);
        device.setJogStep(1);
        for (size_t i = 0; i < 30; i++) {
            device.jog();
            device.wait_for_command(2, 1);
            std::cout << "Device is at " << device.getPos() << " degrees" << std::endl;
            Sleep(500);
        }
        device.stopPolling();
    }

    return 0;
}
