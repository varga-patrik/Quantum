#include <stdio.h>
#include <stdlib.h>
//megjegyzes, ez nem tudom mi de a peldaprogramok szerint kell, elmeletileg minden mukodik nelkule is, de nem art
#include <conio.h>
#include <iostream>
//nyilvan kell hogy telepitve legyen, es hogy megfelelo konyvtarban legyen
#include "Thorlabs.MotionControl.IntegratedStepperMotors.h"

class KinesisUtil {
private:
	std::string serialNum;
	bool connected;
	bool active;
	WORD messageType;
	WORD messageId;
	DWORD messageData;
	double acc, speed;

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
		active = true;
		messageType = 0;
		messageId = 0;
		messageData = 0;
		acc = 0;
		speed = 0;
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
	bool isActive() {
		return active;
	}

	double getAcc(){
		return acc;
	}

	double getSpeed(){
		return speed;
	}

	//minden fuggveny meghivja a nevehez tartozo fuggvenyet az eszkoznek, illetve ellenorzi a kapcsolatot es az aktiv allapotot
	//az 'active' valtozo nem kapcsolja ki az eszkozt, illetve a kapcsolatot sem szunteti meg, csak a fuggvenyeket teszi elerhetetlenne
	//ez azert kell hogy konnyen lehessen kezelni ha tobb eszkoz kozul egynek mar megtalaltuk az optimalis poziciojat
	//ezen kivul minden fuggveny visszater vagy az eredeti fuggveny hibakodjaval, vagy egy bool valtozoval ami jelzi a sikeres vegrehajtast

	std::string getSerial(){
		return serialNum;
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
	bool setJogMode(MOT_JogModes mode);
	bool stopMoving(MOT_StopModes mode);
	bool moveToPosition(double degree);
	bool setAbsParam(double degree);
	bool moveAbs();
	bool setRelParam(double degree);
	bool moveRel();
	double getPos();
	bool canMove();
	bool setVelParams(double acceleration, double maxspeed);
};
