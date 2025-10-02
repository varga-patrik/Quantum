#include <stdio.h>
#include <stdlib.h>
//megjegyzes, ez nem tudom mi de a peldaprogramok szerint kell, elmeletileg minden mukodik nelkule is, de nem art
#include <conio.h>
#include <iostream>
//nyilvan kell hogy telepitve legyen, es hogy megfelelo konyvtarban legyen
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

	//minden fuggveny meghivja a nevehez tartozo fuggvenyet az eszkoznek, illetve ellenorzi a kapcsolatot es az aktiv allapotot
	//az 'active' valtozo nem kapcsolja ki az eszkozt, illetve a kapcsolatot sem szunteti meg, csak a fuggvenyeket teszi elerhetetlenne
	//ez azert kell hogy konnyem lehessen kezelni ha tobb eszkoz kozul egynek mar megtalaltuk az optimalis poziciojat
	//ezen kivul minden fuggveny visszater vagy az eredeti fuggveny hibakodjaval, vagy egy bool valtozoval ami jelzi a sikeres vegrehajtast
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
