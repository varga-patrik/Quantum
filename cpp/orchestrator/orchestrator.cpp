#include "orchestrator.h"

Orchestrator::Orchestrator(
    FSUtil& fsu,
    KinesisUtil& l2c,
    double l2s,
    KinesisUtil& l4c,
    double l4s,
    Correlator& corr,
    const std::string& dataFolderPath,
    double stepDeg
) :
    fs(fsu),
    lambda2_client(l2c),
    lambda2_server(l2s),
    lambda4_client(l4c),
    lambda4_server(l4s),
    correlator(corr),
    currentStep(OrchestratorStep::HomeAll),
    dataFolder(dataFolderPath),
    degreeStep(stepDeg),
    numAngleBins(static_cast<size_t>(180.0 / stepDeg)),
    lastMeasurementType(MeasurementType::FullPhase),
    lastMeasurementStartTime(""),
    lastMeasurementStartTimePico(0),
    totalCoincidences(0),
    stationTimeOffset(0),
    currentVisibility(0.0),
    previousVisibility(0.0),
    visibilityThreshold(0.01),
    qwpSideIndex(0),
    qwpPhase(0),
    qwpTestIndex(0),
    qwpBestVisibility(0.0),
    qwpBestAngle(0.0),
    qwpImprovedLastScan(true)
{
    coincidenceBins.resize(numAngleBins, 0);
    qwpCurrentAngle[0] = 0.0;
    qwpCurrentAngle[1] = 0.0;
    
    //std::cout << "[Orchestrator] Initialized with " << numAngleBins << " angle bins (" << degreeStep << "° each)" << std::endl;
}

std::string Orchestrator::runNextStep() {
    switch (currentStep) {
        case OrchestratorStep::HomeAll:
            return stepHomeAll();
            
        case OrchestratorStep::Setup:
            return stepSetup();
            
        case OrchestratorStep::MeasureFullPhase:
            return stepMeasureFullPhase();
            
        case OrchestratorStep::ReadData:
            return stepReadData();
            
        case OrchestratorStep::AnalyzeData:
            return stepAnalyzeData();
              
        case OrchestratorStep::RotateToMinVis:
            return stepRotateToMinVis();
            
        case OrchestratorStep::AdjustQWP:
            return stepAdjustQWP();
            
        case OrchestratorStep::MeasureWithQWP:
            return stepMeasureWithQWP();
            
        case OrchestratorStep::AnalyzeQWPData:
            return stepAnalyzeQWPData();
            
        case OrchestratorStep::ProcessQWPResults:
            return stepProcessQWPResults();
            
        case OrchestratorStep::CheckConvergence:
            return stepCheckConvergence();
            
        case OrchestratorStep::Exit:
            return "exit";
            
        default:
            std::cerr << "[Orchestrator] Unknown step, exiting" << std::endl;
            currentStep = OrchestratorStep::Exit;
            return "exit";
    }
}

std::string Orchestrator::stepHomeAll() {
    //std::cout << "[Orchestrator] Step: HomeAll" << std::endl;
    
    lambda2_client.home();
    lambda4_client.home();
    
    lambda2_server = 0.0;
    lambda4_server = 0.0;
    
    qwpCurrentAngle[0] = 0.0;
    qwpCurrentAngle[1] = 0.0;
    
    currentStep = OrchestratorStep::Setup;
    return "home";
}

std::string Orchestrator::stepSetup() {
    //std::cout << "[Orchestrator] Step: Setup" << std::endl;
    
    clearDataFolder();
    currentStep = OrchestratorStep::MeasureFullPhase;
    return "setup";
}

std::string Orchestrator::stepMeasureFullPhase() {
    //std::cout << "[Orchestrator] Step: MeasureFullPhase" << std::endl;
    
    lastMeasurementType = MeasurementType::FullPhase;
    lastMeasurementStartTime = fs.start_time();
    lastMeasurementStartTimePico = parseGPSTime(lastMeasurementStartTime);
    
    //std::cout << "[Orchestrator] Starting full phase measurement at " << lastMeasurementStartTime << std::endl;
    
    currentStep = OrchestratorStep::ReadData;
    return "rotate wigner2 full_phase " + FULL_PHASE_DURATION + " " + lastMeasurementStartTime;
}

std::string Orchestrator::stepReadData() {
    //std::cout << "[Orchestrator] Step: ReadData" << std::endl;
    
    currentStep = OrchestratorStep::AnalyzeData;
    return "read_data_file";
}

std::string Orchestrator::stepAnalyzeData() {
    //std::cout << "[Orchestrator] Step: AnalyzeData" << std::endl;
    
    analyzeCoincidences();
    
    //std::cout << "[Orchestrator] Found " << totalCoincidences << " total coincidences" << std::endl;
    //std::cout << "[Orchestrator] Visibility = " << currentVisibility << std::endl;
    
    //std::cout << "[Orchestrator] Coincidence distribution:" << std::endl;
    for (size_t i = 0; i < std::min(size_t(10), coincidenceBins.size()); ++i) {
        //std::cout << "  Bin " << i << " (" << i * degreeStep << "°): " << coincidenceBins[i] << std::endl;
    }
    
    currentStep = OrchestratorStep::RotateToMinVis;
    return "no_command";
}

std::string Orchestrator::stepRotateToMinVis() {
    //std::cout << "[Orchestrator] Step: RotateToMinVis" << std::endl;
    
    if (coincidenceBins.empty() || totalCoincidences == 0) {
        std::cerr << "[Orchestrator] No coincidence data, skipping to QWP adjustment" << std::endl;
        currentStep = OrchestratorStep::AdjustQWP;
        return "no_command";
    }
    
    size_t minBin = findMinVisibilityBin();
    double targetAngle = (static_cast<double>(minBin) + 0.5) * degreeStep;
    
    //std::cout << "[Orchestrator] Rotating λ/2 to minimum visibility angle: " << targetAngle << "° (bin " << minBin << ")" << std::endl;
    
    lambda2_server = targetAngle;
    currentStep = OrchestratorStep::AdjustQWP;
    
    std::ostringstream cmd;
    cmd << "rotate wigner2 " << std::fixed << std::setprecision(2) << targetAngle;
    return cmd.str();
}

std::string Orchestrator::stepAdjustQWP() {
    //std::cout << "[Orchestrator] Step: AdjustQWP" << std::endl;
    
    if (qwpTestIndex == 0 && qwpTestAngles.empty()) {
        bool fineScan = (qwpPhase == 1);
        initializeQWPScan(fineScan);
        
        //std::cout << "[Orchestrator] Initialized " << (fineScan ? "fine" : "coarse") << " QWP scan on " << (qwpSideIndex == 0 ? "client" : "server") << " with " << qwpTestAngles.size() << " angles" << std::endl;
    }
    
    if (isQWPScanComplete()) {
        //std::cout << "[Orchestrator] QWP scan complete, processing results" << std::endl;
        currentStep = OrchestratorStep::ProcessQWPResults;
        return "no_command";
    }
    
    double testAngle = qwpTestAngles[qwpTestIndex];
    std::string deviceName = getQWPDeviceName();
    
    //std::cout << "[Orchestrator] Testing QWP angle " << (qwpTestIndex + 1) << "/" << qwpTestAngles.size() << ": " << testAngle << "° on " << deviceName << std::endl;
    
    if (qwpSideIndex == 0) {
        qwpCurrentAngle[0] = testAngle;
    } else {
        qwpCurrentAngle[1] = testAngle;
    }
    
    currentStep = OrchestratorStep::MeasureWithQWP;
    
    std::ostringstream cmd;
    cmd << "rotate " << deviceName << " " << std::fixed << std::setprecision(2) << testAngle;
    return cmd.str();
}

std::string Orchestrator::stepMeasureWithQWP() {
    //std::cout << "[Orchestrator] Step: MeasureWithQWP" << std::endl;
    
    lastMeasurementType = MeasurementType::FineScan;
    lastMeasurementStartTime = fs.start_time();
    lastMeasurementStartTimePico = parseGPSTime(lastMeasurementStartTime);
    
    //std::cout << "[Orchestrator] Starting fine scan at QWP angle " << qwpCurrentAngle[qwpSideIndex] << "°, time " << lastMeasurementStartTime << std::endl;
    
    currentStep = OrchestratorStep::ReadData;
    
    return "rotate wigner2 fine_scan " + FINE_SCAN_DURATION + " " + lastMeasurementStartTime;
}

std::string Orchestrator::stepAnalyzeQWPData() {
    //std::cout << "[Orchestrator] Step: AnalyzeQWPData" << std::endl;
    
    analyzeCoincidences();
    
    //std::cout << "[Orchestrator] QWP test angle " << qwpCurrentAngle[qwpSideIndex] << "° gave visibility = " << currentVisibility << std::endl;
    
    qwpTestVisibilities.push_back(currentVisibility);
    qwpTestIndex++;
    
    if (isQWPScanComplete()) {
        currentStep = OrchestratorStep::ProcessQWPResults;
    } else {
        currentStep = OrchestratorStep::AdjustQWP;
    }
    
    return "no_command";
}

std::string Orchestrator::stepProcessQWPResults() {
    //std::cout << "[Orchestrator] Step: ProcessQWPResults" << std::endl;
    
    updateQWPBestAngle();
    
    //std::cout << "[Orchestrator] Best QWP angle: " << qwpBestAngle << "° with visibility " << qwpBestVisibility << std::endl;
    
    advanceQWPOptimization();
    
    return "no_command";
}

std::string Orchestrator::stepCheckConvergence() {
    //std::cout << "[Orchestrator] Step: CheckConvergence" << std::endl;
    
    if (hasConverged()) {
        std::cout << "[Orchestrator] Optimization converged! Final visibility = " << currentVisibility << std::endl;
        currentStep = OrchestratorStep::Exit;
        return "exit";
    }
    
    //std::cout << "[Orchestrator] Not converged, starting new full phase measurement" << std::endl;
    previousVisibility = currentVisibility;
    clearDataFolder();
    currentStep = OrchestratorStep::MeasureFullPhase;
    return "no_command";
}

void Orchestrator::analyzeCoincidences() {
    std::fill(coincidenceBins.begin(), coincidenceBins.end(), 0);
    totalCoincidences = 0;
    
    std::vector<std::string> clientFiles = collectDataFiles("bme");
    std::vector<std::string> serverFiles = collectDataFiles("wigner");
    
    if (clientFiles.empty() || serverFiles.empty()) {
        std::cerr << "[Orchestrator] No data files found!" << std::endl;
        currentVisibility = 0.0;
        return;
    }
    
    //std::cout << "[Orchestrator] Found " << clientFiles.size() << " client files and " << serverFiles.size() << " server files" << std::endl;
    
    size_t numPairs = std::min(clientFiles.size(), serverFiles.size());
    for (size_t i = 0; i < numPairs; ++i) {
        std::filesystem::path clientPath = std::filesystem::path(dataFolder) / clientFiles[i];
        std::filesystem::path serverPath = std::filesystem::path(dataFolder) / serverFiles[i];
        
        //std::cout << "[Orchestrator] Processing pair " << (i + 1) << "/" << numPairs << std::endl;
        
        std::vector<int64_t> clientTS = loadTimestampsFromFile(clientPath);
        std::vector<int64_t> serverTS = loadTimestampsFromFile(serverPath);
        
        //std::cout << "[Orchestrator]   Client: " << clientTS.size() << " timestamps" << std::endl;
        //std::cout << "[Orchestrator]   Server: " << serverTS.size() << " timestamps" << std::endl;
        
        std::vector<int64_t> coincidenceTS = findCoincidences(clientTS, serverTS, 10000);
        
        //std::cout << "[Orchestrator]   Found " << coincidenceTS.size() << " coincidences" << std::endl;
        
        double rotationSpeed = getRotationSpeed(lastMeasurementType);
        binCoincidencesByAngle(coincidenceTS, rotationSpeed);
    }
    
    currentVisibility = computeVisibility();
}

std::vector<std::string> Orchestrator::collectDataFiles(const std::string& condition) {
    std::vector<std::string> files;
    
    try {
        if (!std::filesystem::exists(dataFolder)) {
            std::cerr << "[Orchestrator] Data folder doesn't exist: " << dataFolder << std::endl;
            return files;
        }
        
        for (const auto& entry : std::filesystem::directory_iterator(dataFolder)) {
            if (!entry.is_regular_file()) continue;
            
            std::string filename = entry.path().filename().string();
            if (filename.find(condition) != std::string::npos) {
                files.push_back(filename);
            }
        }
    } catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "[Orchestrator] Filesystem error: " << e.what() << std::endl;
    }
    
    return files;
}

std::vector<int64_t> Orchestrator::loadTimestampsFromFile(const std::filesystem::path& filepath) {
    std::vector<int64_t> timestamps;
    
    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) {
        std::cerr << "[Orchestrator] Cannot open file: " << filepath << std::endl;
        return timestamps;
    }
    
    uint64_t picosec, refSec;
    while (file.read(reinterpret_cast<char*>(&picosec), sizeof(uint64_t)) &&
           file.read(reinterpret_cast<char*>(&refSec), sizeof(uint64_t))) {
        
        int64_t absoluteTime = static_cast<int64_t>(picosec) + 
                               static_cast<int64_t>(refSec) * 1000000000000LL;
        timestamps.push_back(absoluteTime);
    }
    
    return timestamps;
}

std::vector<int64_t> Orchestrator::findCoincidences(
    const std::vector<int64_t>& clientTimestamps,
    const std::vector<int64_t>& serverTimestamps,
    int64_t tolerancePico
) {
    std::vector<int64_t> coincidences;
    
    if (clientTimestamps.empty() || serverTimestamps.empty()) {
        return coincidences;
    }
    
    size_t j = 0;
    for (int64_t clientTime : clientTimestamps) {
        int64_t adjustedClientTime = clientTime + stationTimeOffset;
        
        while (j < serverTimestamps.size() && 
               serverTimestamps[j] < adjustedClientTime - tolerancePico) {
            ++j;
        }
        
        if (j < serverTimestamps.size() && 
            std::abs(serverTimestamps[j] - adjustedClientTime) <= tolerancePico) {
            int64_t coincidenceTime = (adjustedClientTime + serverTimestamps[j]) / 2;
            coincidences.push_back(coincidenceTime);
        }
    }
    
    return coincidences;
}

void Orchestrator::binCoincidencesByAngle(
    const std::vector<int64_t>& coincidenceTimestamps,
    double rotationSpeed
) {
    for (int64_t timestamp : coincidenceTimestamps) {
        int64_t elapsedPico = timestamp - lastMeasurementStartTimePico;
        
        double elapsedSec = static_cast<double>(elapsedPico) / 1e12;
        
        double angle = elapsedSec * rotationSpeed;
        
        size_t binIndex = static_cast<size_t>(angle / degreeStep);
        
        if (binIndex < numAngleBins) {
            coincidenceBins[binIndex]++;
            totalCoincidences++;
        }
    }
}

double Orchestrator::computeVisibility() const {
    if (coincidenceBins.empty() || totalCoincidences == 0) {
        return 0.0;
    }
    
    auto minmax = std::minmax_element(coincidenceBins.begin(), coincidenceBins.end());
    double C_min = static_cast<double>(*minmax.first);
    double C_max = static_cast<double>(*minmax.second);
    
    if (C_max + C_min == 0.0) {
        return 0.0;
    }
    
    return (C_max - C_min) / (C_max + C_min);
}

size_t Orchestrator::findMinVisibilityBin() {
    if (coincidenceBins.empty()) {
        return 0;
    }
    
    auto minIt = std::min_element(coincidenceBins.begin(), coincidenceBins.end());
    return std::distance(coincidenceBins.begin(), minIt);
}

void Orchestrator::initializeQWPScan(bool fineScan) {
    qwpTestAngles.clear();
    qwpTestVisibilities.clear();
    qwpTestIndex = 0;
    
    double currentAngle = qwpCurrentAngle[qwpSideIndex];
    double step = fineScan ? QWP_FINE_STEP : QWP_COARSE_STEP;
    double range = fineScan ? QWP_FINE_RANGE : QWP_COARSE_RANGE;
    
    for (double delta = -range; delta <= range + 0.001; delta += step) {
        qwpTestAngles.push_back(currentAngle + delta);
    }
    
    //std::cout << "[Orchestrator] QWP scan: " << qwpTestAngles.size() << " angles from " << (currentAngle - range) << "° to " << (currentAngle + range) << "°" << std::endl;
}

bool Orchestrator::isQWPScanComplete() {
    return qwpTestIndex >= qwpTestAngles.size();
}

bool Orchestrator::areBothQWPSidesOptimized() {
    return (qwpSideIndex == 1 && qwpPhase == 1 && !qwpImprovedLastScan);
}

std::string Orchestrator::getQWPDeviceName() {
    return (qwpSideIndex == 0) ? "bme4" : "wigner4";
}

void Orchestrator::updateQWPBestAngle() {
    if (qwpTestVisibilities.empty()) {
        std::cerr << "[Orchestrator] No QWP test results!" << std::endl;
        return;
    }
    
    auto maxIt = std::max_element(qwpTestVisibilities.begin(), qwpTestVisibilities.end());
    size_t maxIndex = std::distance(qwpTestVisibilities.begin(), maxIt);
    
    double newBestVisibility = *maxIt;
    double newBestAngle = qwpTestAngles[maxIndex];
    
    //std::cout << "[Orchestrator] Scan results:" << std::endl;
    for (size_t i = 0; i < qwpTestAngles.size(); ++i) {
        //std::cout << "  Angle " << qwpTestAngles[i] << "°: visibility = " << qwpTestVisibilities[i] << std::endl;
    }
    
    if (newBestVisibility > qwpBestVisibility + QWP_MIN_IMPROVEMENT) {
        qwpImprovedLastScan = true;
        qwpBestVisibility = newBestVisibility;
        qwpBestAngle = newBestAngle;
        qwpCurrentAngle[qwpSideIndex] = newBestAngle;
        
        //std::cout << "[Orchestrator] Improvement found! New best: " << qwpBestAngle << "° with visibility " << qwpBestVisibility << std::endl;
    } else {
        qwpImprovedLastScan = false;
        //std::cout << "[Orchestrator] No significant improvement." << std::endl;
    }
}

void Orchestrator::advanceQWPOptimization() {
    if (qwpPhase == 0) {
        if (qwpImprovedLastScan) {
            //std::cout << "[Orchestrator] Coarse scan improved, starting fine scan on same side" << std::endl;
            qwpPhase = 1;
            initializeQWPScan(true);
            currentStep = OrchestratorStep::AdjustQWP;
        } else {
            if (qwpSideIndex == 0) {
                //std::cout << "[Orchestrator] No coarse improvement on client, moving to server" << std::endl;
                qwpSideIndex = 1;
                qwpPhase = 0;
                initializeQWPScan(false);
                currentStep = OrchestratorStep::AdjustQWP;
            } else {
                //std::cout << "[Orchestrator] Both sides scanned, checking convergence" << std::endl;
                currentStep = OrchestratorStep::CheckConvergence;
            }
        }
    } else {
        if (qwpImprovedLastScan) {
            //std::cout << "[Orchestrator] Fine scan improved, repeating fine scan" << std::endl;
            initializeQWPScan(true);
            currentStep = OrchestratorStep::AdjustQWP;
        } else {
            if (qwpSideIndex == 0) {
                //std::cout << "[Orchestrator] Client side optimized, moving to server" << std::endl;
                qwpSideIndex = 1;
                qwpPhase = 0;
                initializeQWPScan(false);
                currentStep = OrchestratorStep::AdjustQWP;
            } else {
                //std::cout << "[Orchestrator] Both QWP sides optimized, checking convergence" << std::endl;
                currentStep = OrchestratorStep::CheckConvergence;
            }
        }
    }
}

void Orchestrator::clearDataFolder() {
    try {
        if (!std::filesystem::exists(dataFolder)) {
            //std::cout << "[Orchestrator] Creating data folder: " << dataFolder << std::endl;
            std::filesystem::create_directories(dataFolder);
            return;
        }
        
        int filesDeleted = 0;
        for (const auto& entry : std::filesystem::directory_iterator(dataFolder)) {
            if (std::filesystem::is_regular_file(entry)) {
                std::filesystem::remove(entry);
                filesDeleted++;
            }
        }
        
        //std::cout << "[Orchestrator] Cleared " << filesDeleted << " files from data folder" << std::endl;
        
    } catch (const std::exception& e) {
        std::cerr << "[Orchestrator] Error clearing data folder: " << e.what() << std::endl;
    }
}

int64_t Orchestrator::parseGPSTime(const std::string& gpsTimeStr) {
    int hour, minute, second;
    char comma1, comma2, dot;
    char picoStr[13];
    
    std::istringstream iss(gpsTimeStr);
    iss >> hour >> comma1 >> minute >> comma2 >> second >> dot;
    iss.get(picoStr, 13);
    
    std::string picoString(picoStr);
    while (picoString.length() < 12) {
        picoString += '0';
    }
    
    uint64_t picoseconds = std::stoull(picoString);
    
    int64_t totalPico = static_cast<int64_t>(hour) * 3600LL * 1000000000000LL +
                        static_cast<int64_t>(minute) * 60LL * 1000000000000LL +
                        static_cast<int64_t>(second) * 1000000000000LL +
                        static_cast<int64_t>(picoseconds);
    
    return totalPico;
}

double Orchestrator::getRotationSpeed(MeasurementType type) {
    return (type == MeasurementType::FullPhase) ? 
           FULL_PHASE_ROTATION_SPEED : FINE_SCAN_ROTATION_SPEED;
}

bool Orchestrator::hasConverged() {
    double change = std::abs(currentVisibility - previousVisibility);
    
    //std::cout << "[Orchestrator] Convergence check: current=" << currentVisibility << ", previous=" << previousVisibility << ", change=" << change << ", threshold=" << visibilityThreshold << std::endl;
    
    return change < visibilityThreshold;
}