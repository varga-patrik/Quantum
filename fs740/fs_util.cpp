#include "fs_util.h"

#pragma comment (lib, "Ws2_32.lib")

void FSUtil::run(std::string path){
    STARTUPINFOA si;
    PROCESS_INFORMATION pi;

    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    std::string command;
    if(path.find(".py")!=std::string::npos){
        command =  "python " + path;
    }
    else{
        command = path;
    }

    std::cout << "Now running command: " << command << " at " << print_gpstime() <<std::endl;

    bool success = CreateProcessA(
        NULL,       // lpApplicationName
        (char*)command.c_str(),    // lpCommandLine (must be mutable)
        NULL,
        NULL,
        FALSE,
        0,
        NULL,
        NULL,
        &si,
        &pi
    );

    if (!success) {
        std::cerr << "CreateProcess failed with error code: " << GetLastError() << '\n';
        return;
    }

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    std::cout << "Finished running proccess at " << print_gpstime() << std::endl;
}

bool FSUtil::is_same_str(const char* str1, const char* str2){
    for(int i=0; str1[i]!='\0' || str2[i]!='\0'; i++){
        if(str1[i]!='\0' && str2[i]=='\0' || str2[i]!='\0' && str1[i]=='\0'){
            return false;
        }
        if(str1[i]!=str2[i]){
            return false;
        }
    }
    return true;
}

void FSUtil::init_tcpip(void)
{
    WSADATA wsadata;
    if ( WSAStartup(2, &wsadata) != 0 ) {
        printf("Unable to load windows socket library\n");
        exit(1);
    }
}

int FSUtil::fs740_connect(unsigned long ip)
{
    /* Connect to the FS740 */
    struct sockaddr_in intrAddr;
    int status;
    sFS740 = socket(AF_INET,SOCK_STREAM,0);
    if ( sFS740 == INVALID_SOCKET )
    return 0;
    /* Bind to a local port */
    memset(&intrAddr,0,sizeof(intrAddr));
    intrAddr.sin_family = AF_INET;
    intrAddr.sin_port = htons(0);
    intrAddr.sin_addr.S_un.S_addr = htonl(INADDR_ANY);
    if ( SOCKET_ERROR == bind(sFS740,(const struct sockaddr *)&intrAddr,sizeof(intrAddr)) ) {
    closesocket(sFS740);
    sFS740 = INVALID_SOCKET;
    return 0;
    }
    /* Setup address for the connection to fs740 on port 5025 */
    memset(&intrAddr,0,sizeof(intrAddr));
    intrAddr.sin_family = AF_INET;
    intrAddr.sin_port = htons(5025);
    intrAddr.sin_addr.S_un.S_addr = ip;
    status = connect(sFS740,(const struct sockaddr *)&intrAddr,sizeof(intrAddr));
    if ( status ) {
    closesocket(sFS740);
    sFS740 = INVALID_SOCKET;
    return 0;
    }
    return 1;
}

int FSUtil::fs740_close(void)
{
    if (connected){
        if ( closesocket(sFS740) != SOCKET_ERROR )
        return 1;
        else
        return 0;
    }
    return 0;
}

int FSUtil::fs740_write(const char *str)
{
    if (connected){
        /* Write string to connection */
        int result;

        result = send(sFS740,str,(int)strlen(str),0);
        if ( SOCKET_ERROR == result )
        result = 0;
        return result;
    }
    return 0;
}

int FSUtil::fs740_write_bytes(const void *data, unsigned num)
{
    if(connected){
        /* Write string to connection */
        int result;

        result = send(sFS740,(const char *)data,(int)num,0);
        if ( SOCKET_ERROR == result )
        result = 0;
        return result;
    }
    return 0;
}

int FSUtil::fs740_read(char *buffer, unsigned num)
{
    if (connected){
        /* Read up to num bytes from connection */
        int count;
        fd_set setRead, setWrite, setExcept;
        TIMEVAL tm;

        /* Use select() so we can timeout gracefully */
        tm.tv_sec = fs740_timeout/1000;
        tm.tv_usec = (fs740_timeout % 1000) * 1000;
        FD_ZERO(&setRead);
        FD_ZERO(&setWrite);
        FD_ZERO(&setExcept);
        FD_SET(sFS740,&setRead);
        count = select(0,&setRead,&setWrite,&setExcept,&tm);
        if ( count == SOCKET_ERROR ) {
            printf("select failed: connection aborted\n");
            closesocket(sFS740);
            exit(1);
        }
        count = 0;
        if ( FD_ISSET(sFS740,&setRead) ) {
            /* We've received something */
            count = (int)recv(sFS740,buffer,num-1,0);
            if ( SOCKET_ERROR == count ) {
                printf("Receive failed: connection aborted\n");
                closesocket(sFS740);
                exit(1);
            }
            else if (count ) {
                
            }
            else {
                printf("Connection closed by remote host\n");
                closesocket(sFS740);
                exit(1);
            }
        }
        return count;
    }
    return 0;
}

std::string FSUtil::precise_computer_time(){
    auto now = std::chrono::system_clock::now();

	// Convert to time_t for HH:MM:SS
	std::time_t nowTimeT = std::chrono::system_clock::to_time_t(now);
	std::tm* nowTm = std::gmtime(&nowTimeT); 

	// Duration since epoch
	auto durationSinceEpoch = now.time_since_epoch();
	auto seconds = std::chrono::duration_cast<std::chrono::seconds>(durationSinceEpoch);
	auto nanos = std::chrono::duration_cast<std::chrono::nanoseconds>(durationSinceEpoch - seconds).count();

    std::ostringstream strStream;
    strStream << std::put_time(nowTm, "%H,%M,%S") << "." 
	    << std::setw(9) << std::setfill('0') << nanos;

    return strStream.str();
}

int64_t FSUtil::calculate_time_diff(const char *buff1, const char* buff2) {
	// Parse input: HH,MM,SS.picoseconds
	int hour1, minute1;
	char secFrac1[64];
	if (sscanf(buff1, "%d,%d,%63s", &hour1, &minute1, secFrac1) != 3) {
		std::cerr << "Invalid format\n";
		return 0;
	}

    int hour2, minute2;
	char secFrac2[64];
	if (sscanf(buff2, "%d,%d,%63s", &hour2, &minute2, secFrac2) != 3) {
		std::cerr << "Invalid format\n";
		return 0;
	}

	// Split "SS.picosec" into seconds and fractional part
	char* dotPtr1 = strchr(secFrac1, '.');
	if (!dotPtr1) {
		std::cerr << "Missing fractional seconds\n";
		return 0;
	}

	*dotPtr1 = '\0'; // Null-terminate seconds part
	int second1 = atoi(secFrac1);
	const char* picoStr1 = dotPtr1 + 1;

    // Split "SS.picosec" into seconds and fractional part
	char* dotPtr2 = strchr(secFrac2, '.');
	if (!dotPtr2) {
		std::cerr << "Missing fractional seconds\n";
		return 0;
	}

	*dotPtr2 = '\0'; // Null-terminate seconds part
	int second2 = atoi(secFrac2);
	const char* picoStr2 = dotPtr2 + 1;

	// Normalize to 12-digit picoseconds (pad with zeros if needed)
	char picoFull1[13] = "000000000000";
	strncpy(picoFull1, picoStr1, std::min((size_t)12, strlen(picoStr1)));
	uint64_t picoseconds1 = std::strtoull(picoFull1, nullptr, 10);

	// Total picoseconds since midnight for input
	int64_t buff1Picoseconds = static_cast<int64_t>(
		((hour1 * 3600LL + minute1 * 60LL + second1) * 1'000'000'000'000LL) + picoseconds1);

    char picoFull2[13] = "000000000000";
	strncpy(picoFull2, picoStr2, std::min((size_t)12, strlen(picoStr2)));
	uint64_t picoseconds2 = std::strtoull(picoFull2, nullptr, 10);

	// Total picoseconds since midnight for input
	int64_t buff2Picoseconds = static_cast<int64_t>(
		((hour2 * 3600LL + minute2 * 60LL + second2) * 1'000'000'000'000LL) + picoseconds2);

	// Return delta (input - now)
	return buff1Picoseconds - buff2Picoseconds;
}

void FSUtil::wait_until(const char* t){
    if (connected){
        while(!is_earlier_time(t, buffer)){
            fs740_write("syst:time?\n");
            fs740_read(buffer,sizeof(buffer));    
        }
        /*double diff = abs((double)calculate_time_diff(t, print_gpstime().c_str()) / 1000000000000);
        int seconds = (int) diff;
        int microsec = (int) (diff-seconds)*1000000;
        std::this_thread::sleep_for(std::chrono::seconds(seconds));
        std::this_thread::sleep_for(std::chrono::microseconds(microsec));*/
    }
}

bool FSUtil::is_earlier_time(const char* early, const char* late){
    return calculate_time_diff(early, late) < 0;
}

void FSUtil::write_diff_to_file(double delta, const std::string& filename = "diff_data.csv") {
    std::ofstream outFile(filename, std::ios::app);
    if (!outFile) {
        std::cerr << "Failed to open file: " << filename << std::endl;
        return;
    }

    outFile << delta << '\n';
    outFile.close();
}

void FSUtil::scpi_terminal(){
    if(connected){
        std::string command;
        while(command!="exit\n"){
            std::cin >> command;
            command.push_back('\n');
            fs740_write(command.c_str());
            if(command.find("?")!=std::string::npos){
                if ( fs740_read(buffer,sizeof(buffer)) )
                    printf(buffer);
                else
                    printf("Timeout or wrong command\n");
            }
        }
    }
}

std::string FSUtil::start_time(){
    if(connected){
        fs740_write("syst:time?\n");
        if(fs740_read(buffer, sizeof(buffer))){
            int hour, minute; double second;
            sscanf(buffer, "%d,%d,%lf", &hour, &minute, &second);

            second++;
            second++;
            if(second >= 60){
                second -= 60;
                minute++;
            }

            if(minute >= 60) {
                minute -= 60;
                hour++;
            }

            if(hour >= 24){
                hour -=24;
            }

            std::ostringstream new_time;
            new_time << hour << "," << minute << "," << (int)second << ".650000000000"; //egyelőre .982 a vége mivel kb így lesz közel az új másodperc kezdetéhez
            return new_time.str();
        }
        else
            return std::string("Timeout");
    }
    return std::string("Not connected");
}

void FSUtil::measure_setup(){
    if(connected){
        fs740_write("sour3:func puls\n");
        fs740_write("sour3:freq 1Hz\n");
        fs740_write("sour3:puls:dcyc 0.0001%\n");
        fs740_write("sour3:phas:sync\n");
    }
}

void FSUtil::measure_timedrift(int steps){
    if(connected){
        for(int i = 0; i < steps; i++){
            std::string computer_time = precise_computer_time();
            fs740_write("syst:time?\n");
            if ( fs740_read(buffer,sizeof(buffer))) {
                printf("GPS CLOCK:   ");
                printf(buffer);
                std::cout << "LOCAL TIME: " << computer_time << std::endl;
                double diff = (double)calculate_time_diff(buffer, computer_time.c_str()) / 1000000000000;
                std::cout << (i+1) << ". " << "TIME DIFF:        " << diff << std::endl;
                write_diff_to_file(diff, "diff_data.csv");
            }
            else {
                printf("Timeout\n"); 
            }        
            std::this_thread::sleep_for(std::chrono::seconds(1));
        }
    }
}

std::string FSUtil::print_gpstime(){
    if(connected){
        fs740_write("syst:time?\n");
        if ( fs740_read(buffer,sizeof(buffer))) {
            return std::string(buffer);
        }
    }
    return std::string("Not connected");
}

bool FSUtil::is_in(const char* str, const char* substr){
    std::string _str = str;
    std::string _substr = substr;

    return _str.find(_substr) != std::string::npos;
}