#include "KinesisUtil.h"

//kapcsolodas az eszkozhoz
bool KinesisUtil::connect() {
    std::cout << "Connecting to " << serialNum << std::endl;
	short errorCode;
	errorCode = ISC_Open(serialNum.c_str());
	return errorCode == 0;
}

//varakozas a megadott parancs lefutasara
//nagyon konnyu egy vegtelen ciklust csinalni, ha rossz id-t adunk meg, meg neha amugy sem mukodik
//a leiras szerint egy generic motors eszkozokre (mint amilyen az az eszkoz is amire eredetileg keszult a kod) az alabbi id-k vannak:
//homed: 0, moved: 1, stopped: 2, limitUpdated: 3
//message type mindig kettő generic motor eseten
void KinesisUtil::wait_for_command(WORD type, WORD id) { //id = 0 ha home, mozgasnal 1
    if (connected && active) {
        ISC_WaitForMessage(serialNum.c_str(), &messageType, &messageId, &messageData);
        while (messageType != type || messageId != id)
        {
            ISC_WaitForMessage(serialNum.c_str(), &messageType, &messageId, &messageData);
        }
    }
}

//betolti az eszkoz beallitasait
//megjegyzes, nagyon sokat olvastam a leirast, de nem tudom pontosan hol vannak ezek a beallitasok
//azt sem tudom lehet e ezt a beallitast manipulalni, vagy csak olvasasra van
//van egy loadNamedSettings is, de arra sem talaltam semmit hogyan lehet olyat letrehozni
//lenyeg a lenyeg, enelkul valamiert egyes funkciok nem futnak le, illetve nagyon lassan forog a motor ha nem futtatjuk le
//enelkul is allithato a forgasi sebesseg de nagyon nem praktikus
bool KinesisUtil::load() {
    if (connected && active) {
        std::cout << "Loading " << serialNum << std::endl;
        bool success = ISC_LoadSettings(serialNum.c_str());
        int acceleration, maxspeed;
        ISC_GetVelParams(serialNum.c_str(), &acceleration, &maxspeed);
        acc = getReal(acceleration, 2);
        speed = getReal(maxspeed, 1);
        return success;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//polling inditasa
bool KinesisUtil::startPolling(int milisec) {
    if (connected && active) {
        std::cout << "Polling " << serialNum << std::endl;
        short errorCode = ISC_StartPolling(serialNum.c_str(), milisec);
        Sleep(3000);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//polling leallitasa
bool KinesisUtil::stopPolling() {
    if (connected && active) {
        std::cout << "Stopping polling with " << serialNum << std::endl;
        ISC_StopPolling(serialNum.c_str());
        return true;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//uzenetek torlese
bool KinesisUtil::clear() {
    if (connected && active) {
        std::cout << "Clearing messages from " << serialNum << std::endl;
        ISC_ClearMessageQueue(serialNum.c_str());
        return true;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//home pozicioba allitas
bool KinesisUtil::home() {
    if (connected && active) {
        std::cout << "Homing " << serialNum << std::endl;
        short errorCode = ISC_Home(serialNum.c_str());
        wait_for_command(2, 0);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//valos ertek atvaltasa eszkoz ertekre
//unit type távolság esetén 0, sebesség 1 és gyorsulás 2
int KinesisUtil::getDevice(double real, int unitType) {
    if (connected && active) {
        short errorCode;
        int deviceUnit;
        errorCode = ISC_GetDeviceUnitFromRealValue(serialNum.c_str(), real, &deviceUnit, unitType);
        return deviceUnit;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return -1;
}

//eszkoz ertek atvaltasa valos ertekre
//unit type távolság esetén 0, sebesség 1 és gyorsulás 2
double KinesisUtil::getReal(int device, int unitType) {
    if (connected && active) {
        short errorCode;
        double realUnit;
        errorCode = ISC_GetRealValueFromDeviceUnit(serialNum.c_str(), device, &realUnit, unitType);
        return realUnit;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return -1;
}

//jog lepes meretenek beallitasa
bool KinesisUtil::setJogStep(double step) {
    if (connected && active) {
        std::cout << "Setting step size for " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_SetJogStepSize(serialNum.c_str(), getDevice(step, 0));
        ISC_SetJogMode(serialNum.c_str(), MOT_SingleStep, MOT_Profiled);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//jog inditasa
bool KinesisUtil::jog() {
    if (connected && active) {
        std::cout << "Jogging " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveJog(serialNum.c_str(), MOT_Forwards);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::setJogMode(MOT_JogModes mode){
    if(connected && active){
        if(mode == MOT_JogModes::MOT_Continuous){
            std::cout << "Setting jog mode to continuous for " << serialNum << std::endl;
        }

        if(mode == MOT_JogModes::MOT_SingleStep){
            std::cout << "Setting jog mode to single step for " << serialNum << std::endl;
        }

        short errorCode;
        errorCode = ISC_SetJogMode(serialNum.c_str(), mode, MOT_StopModes::MOT_Profiled);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::stopMoving(MOT_StopModes mode){
    if(connected && active){
        if(mode == MOT_StopModes::MOT_Immediate){
            std::cout << "Stopping " << serialNum << " with immediate stop mode" << std::endl;
            short errorCode;
            errorCode = ISC_StopImmediate(serialNum.c_str());
            return errorCode == 0;
        }

        if(mode == MOT_StopModes::MOT_Profiled){
            std::cout << "Stopping " << serialNum << " with profiled stop mode" << std::endl;
            short errorCode;
            errorCode = ISC_StopProfiled(serialNum.c_str());
            return errorCode == 0;
        }
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//mozgas adott pozicioba
bool KinesisUtil::moveToPosition(double degree) {
    if (connected && active) {
        std::cout << "Moving " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveToPosition(serialNum.c_str(), getDevice(degree, 0));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//abszolut pozicio beallitasa
bool KinesisUtil::setAbsParam(double degree) {
    if (connected && active) {
        short errorCode;
        errorCode = ISC_SetMoveAbsolutePosition(serialNum.c_str(), getDevice(degree, 0));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//abszolut pozicioba mozgas
bool KinesisUtil::moveAbs() {
    if (connected && active) {
        std::cout << "Moving " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveAbsolute(serialNum.c_str());
        wait_for_command(2, 1);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//egyelore nem jottem ra hogy milyen mertekegysegnek kell ertelmezni a parametereket
bool KinesisUtil::setVelParams(double acceleration, double maxspeed){
    if (connected && active){
        std::cout << "Setting acceleration to " << acceleration << " and speed to " << maxspeed << std::endl;
        acc = acceleration;
        speed = maxspeed;
        short errorCode; 
        errorCode = ISC_SetVelParams(serialNum.c_str(), getDevice(acc, 2), getDevice(speed, 1));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//relativ pozicio beallitasa
bool KinesisUtil::setRelParam(double degree) {
    if (connected && active) {
        short errorCode;
        errorCode = ISC_SetMoveRelativeDistance(serialNum.c_str(), getDevice(degree, 0));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//relativ pozicioba mozgas
bool KinesisUtil::moveRel() {
    if (connected && active) {
        std::cout << "Moving " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveRelativeDistance(serialNum.c_str());
        wait_for_command(2, 1);
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

//aktualis pozicio lekerese, fokokban szamolva
double KinesisUtil::getPos() {
    if (connected && active) {
        return getReal(ISC_GetPosition(serialNum.c_str()), 0);
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return -1;
}

//ellenorzi hogy mozoghat e az eszkoz, ha nem akkor home-olni kell eloszor
bool KinesisUtil::canMove() {
    if (connected && active) {
        return ISC_CanMoveWithoutHomingFirst(serialNum.c_str());
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}