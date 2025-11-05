#include "KinesisUtil.h"
#include <chrono>
#include <vector>
#include <thread>

bool nearTarget(double target, double position){
    return abs(target - position) < 0.5;
}

int main(){
    const char* serial = "55526814";
    std::vector<std::chrono::duration<double>> rotationTimes;

    if(TLI_BuildDeviceList() == 0){
        KinesisUtil device(serial);

        device.activate();
        device.startPolling(200);
        device.load();
        device.home();

        int rotationCounter = 0;

        std::chrono::system_clock::time_point start_time;
        std::chrono::system_clock::time_point end_time;

        device.setVelParams(device.getAcc(), device.getSpeed());
        device.setRelParam(50.0);

        while(rotationCounter != 10) {
            start_time = std::chrono::system_clock::now();
            device.moveRel();
            end_time = std::chrono::system_clock::now();
            rotationTimes.push_back(end_time - start_time);
            rotationCounter++;
            std::cout << "Rotation done" << std::endl;

            /*if(state == HOME){
                start_time = std::chrono::system_clock::now();
                state = TARGET;
            }

            if(state == TARGET){
                end_time = std::chrono::system_clock::now();
                rotationTimes.push_back(end_time - start_time);
                rotationCounter++;
                state = HOME;
                std::cout << "Rotation done" << std::endl;
            }*/
        }

        device.stopPolling();
    }

    for(int i=0; i<rotationTimes.size(); i++){
        std::cout << "[" << i+1 << "] rotation took " << rotationTimes.at(i).count() << std::endl;
    }
}