#include <stdio.h>
#include <stdlib.h>
#include <conio.h>
#include <iostream>
#include "C:\Program Files\Thorlabs\Kinesis\Thorlabs.MotionControl.IntegratedStepperMotors.h"

class KinesisUtil {
private:
	std::string serialNum;
	bool connected;
	bool active;
	WORD messageType;
	WORD messageId;
	DWORD messageData;

public:
	KinesisUtil(const char* serial) {
		serialNum = serial;
		connected = connect();
		if (connected) {
			std::cout << "Connected" << std::endl;
		}
		else {
			std::cout << "Not connected" << std::endl;
		}
		active = false;
		messageType = 0;
		messageId = 0;
		messageData = 0;
	}

	~KinesisUtil() {
		ISC_Close(serialNum.c_str());
	}

	bool connect();
	void activate() {
		active = true;
	}
	void deactivate() {
		active = false;
	}
	void wait_for_command(WORD type, WORD id);
	bool load();
	bool startPolling(int milisec);
	bool stopPolling();
	bool clear();
	bool home();
	int getDevice(double real, int unitType);
	double getReal(int device, int unitType);
	bool setJogStep(double step);
	bool jog();
	bool moveToPosition(double degree);
	bool setAbsParam(double degree);
	bool moveAbs();
	bool setRelParam(double degree);
	bool moveRel();
	double getPos();
	bool canMove();
};
