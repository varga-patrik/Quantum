#include "KinesisUtil.h"

bool KinesisUtil::connect() {
    std::cout << "Connecting to " << serialNum << std::endl;
	short errorCode;
	errorCode = ISC_Open(serialNum.c_str());
	return errorCode == 0;
}

void KinesisUtil::wait_for_command(WORD type, WORD id) {
    if (connected && active) {
        ISC_WaitForMessage(serialNum.c_str(), &messageType, &messageId, &messageData);
        while (messageType != type || messageId != id)
        {
            ISC_WaitForMessage(serialNum.c_str(), &messageType, &messageId, &messageData);
        }
    }
}

bool KinesisUtil::load() {
    if (connected && active) {
        std::cout << "Loading " << serialNum << std::endl;
        return ISC_LoadSettings(serialNum.c_str());
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

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

bool KinesisUtil::stopPolling() {
    if (connected && active) {
        std::cout << "Stopping polling with " << serialNum << std::endl;
        ISC_StopPolling(serialNum.c_str());
        return true;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::clear() {
    if (connected && active) {
        std::cout << "Clearing messages from " << serialNum << std::endl;
        ISC_ClearMessageQueue(serialNum.c_str());
        return true;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::home() {
    if (connected && active) {
        std::cout << "Homing " << serialNum << std::endl;
        short errorCode = ISC_Home(serialNum.c_str());
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

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

bool KinesisUtil::setAbsParam(double degree) {
    if (connected && active) {
        short errorCode;
        errorCode = ISC_SetMoveAbsolutePosition(serialNum.c_str(), getDevice(degree, 0));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::moveAbs() {
    if (connected && active) {
        std::cout << "Moving " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveAbsolute(serialNum.c_str());
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::setRelParam(double degree) {
    if (connected && active) {
        short errorCode;
        errorCode = ISC_SetMoveRelativeDistance(serialNum.c_str(), getDevice(degree, 0));
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

bool KinesisUtil::moveRel() {
    if (connected && active) {
        std::cout << "Moving " << serialNum << std::endl;
        short errorCode;
        errorCode = ISC_MoveRelativeDistance(serialNum.c_str());
        return errorCode == 0;
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}

double KinesisUtil::getPos() {
    if (connected && active) {
        return getReal(ISC_GetPosition(serialNum.c_str()), 0);
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return -1;
}

bool KinesisUtil::canMove() {
    if (connected && active) {
        return ISC_CanMoveWithoutHomingFirst(serialNum.c_str());
    }
    std::cout << "ERROR, not connected or unactive device" << std::endl;
    return false;
}