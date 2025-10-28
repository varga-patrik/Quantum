#include "orchestrator.h"

std::string Orchestrator::runNextStep(){
    switch (stepIndex)
    {
    case 1:
        stepIndex++;
        return homeAll();
    
    case 2:
        stepIndex++;
        return "start " + fs.start_time();

    case 3:
        stepIndex++;
        return "rotate wigner2 180";

    case 4:
        stepIndex++;
        return "read_data_file";

    case 5:
        stepIndex++;
        analyzeData();
        return "no command";
    
    case6:
        stepIndex = 1;
        return runQWPOptimizationStep();
        
    default:
        return "exit";
    }
}

std::string Orchestrator::homeAll(){
    lambda2_client.home();
    lambda2_client.wait_for_command(2, 0);
    lambda2_client.deactivate();

    lambda2_server.home();
    lambda2_server.wait_for_command(2, 0);

    lambda4_server.home();
    lambda4_server.wait_for_command(2, 0);

    lambda4_client.home();
    lambda4_client.wait_for_command(2, 0);

    return "home";
}

void Orchestrator::clearDataFolder(){
    try {
        if (!std::filesystem::exists(dataFolder)) return;

        for (const auto& entry : std::filesystem::directory_iterator(dataFolder)) {
            if (std::filesystem::is_regular_file(entry)) {
                std::filesystem::remove(entry);
            }
        }

    } catch (const std::exception& e) {
        std::cerr << "[Orchestrator] Error clearing data folder: " << e.what() << std::endl;
    }
}



void Orchestrator::analyzeData() {
    coincidences.clear(); // ensure we start fresh

    // Get all relevant client and server files
    std::vector<std::string> clientFiles = collectDataFiles("client");
    std::vector<std::string> serverFiles = collectDataFiles("server");

    std::cout << "Found " << clientFiles.size() << " client files and "
              << serverFiles.size() << " server files.\n";

    // Process each pair of client/server file
    for (size_t i = 0; i < std::min(clientFiles.size(), serverFiles.size()); ++i) {
        std::filesystem::path clientPath = dataFolder / std::filesystem::path(clientFiles[i]);
        std::filesystem::path serverPath = dataFolder / std::filesystem::path(serverFiles[i]);

        // Load timestamps
        std::vector<double> clientTimestamps = loadTimestamps(clientPath);
        std::vector<double> serverTimestamps = loadTimestamps(serverPath);

        // Calculate coincidences and append to member vector
        std::vector<double> localCoincidences =
            calculateCoincidences(clientTimestamps, serverTimestamps, 10.0); // tolerance: 10 ns

        coincidences.insert(coincidences.end(),
                                localCoincidences.begin(),
                                localCoincidences.end());
    }
}


std::vector<std::string> Orchestrator::collectDataFiles(const std::string& condition) {
    std::vector<std::string> files;

    try {
        for (const auto& entry : std::filesystem::directory_iterator(dataFolder)) {
            if (!entry.is_regular_file()) continue; 
            std::string filename = entry.path().filename().string();

            if (filename.find(condition) != std::string::npos) {
                files.push_back(entry.path().string());
            }
        }
    }
    catch (const std::filesystem::filesystem_error& e) {
        std::cerr << "Filesystem error: " << e.what() << std::endl;
    }

    return files;
}

// Example implementation that loads binary timestamps
std::vector<double> Orchestrator::loadTimestamps(const std::filesystem::path& filepath) {
    std::ifstream file(filepath, std::ios::binary);
    if (!file.is_open()) {
        std::cerr << "Error: Cannot open " << filepath << "\n";
        return {};
    }

    std::vector<double> timestamps;
    double value;
    while (file.read(reinterpret_cast<char*>(&value), sizeof(double))) {
        timestamps.push_back(value);
    }

    return timestamps;
}

// Finds timestamps within a given tolerance (in nanoseconds)
std::vector<double> Orchestrator::calculateCoincidences(
    const std::vector<double>& clientTimestamps,
    const std::vector<double>& serverTimestamps,
    double toleranceNs
) {
    std::vector<double> coincidences;

    size_t j = 0;
    for (double ct : clientTimestamps) {
        while (j < serverTimestamps.size() && serverTimestamps[j] < ct - toleranceNs)
            ++j;

        if (j < serverTimestamps.size() && std::abs(serverTimestamps[j] - ct) <= toleranceNs)
            coincidences.push_back((ct + serverTimestamps[j]) / 2.0); // midpoint of coincidence
    }

    return coincidences;
}

double Orchestrator::computeVisibility() const {
    if (coincidences.empty()) return 0.0;
    auto minmax = std::minmax_element(coincidences.begin(), coincidences.end());
    double C_min = static_cast<double>(*minmax.first);
    double C_max = static_cast<double>(*minmax.second);
    if (C_max + C_min == 0.0) return 0.0;
    return (C_max - C_min) / (C_max + C_min);
}

void Orchestrator::prepareQWPScan(bool fine) {
    qwpTestAngles.clear();
    double step = fine ? qwpFineStep : qwpCoarseStep;
    double range = fine ? qwpFineRange : qwpCoarseRange;
    double currentAngle = qwpCurrentAngle[qwpOptSideIndex];
    for (double delta = -range; delta <= range; delta += step)
        qwpTestAngles.push_back(currentAngle + delta);
    qwpTestIndex = 0;
}

std::string Orchestrator::runQWPOptimizationStep() {
    // If fine scan is finished on both sides and no improvement, we are done
    if (!qwpImproved && qwpPhase == 1 && qwpTestIndex >= qwpTestAngles.size()) {
        return "exit"; // entire experiment is converged
    }

    // Prepare scan if just starting
    if (qwpTestIndex == 0 && qwpTestAngles.empty()) {
        prepareQWPScan(qwpPhase == 1); // coarse if phase 0, fine if phase 1
    }

    // If there are remaining angles, return rotation command
    if (qwpTestIndex < qwpTestAngles.size()) {
        double angle = qwpTestAngles[qwpTestIndex++];
        return "rotate wigner " + std::to_string(angle); // server QWP
    } else {
        // All angles tested, update best visibility
        double visibility = computeVisibility();
        if (visibility - qwpBestVisibility > qwpMinImprovement) {
            qwpBestVisibility = visibility;
            qwpCurrentAngle[qwpOptSideIndex] = qwpTestAngles.back();
            qwpImproved = true;
        } else {
            qwpImproved = false;
        }

        // Move to next side or fine scan
        if (qwpPhase == 0) { // coarse scan done
            qwpPhase = 1;
            qwpOptSideIndex = 1 - qwpOptSideIndex;
            prepareQWPScan(true); // fine scan
            return runQWPOptimizationStep(); // immediately provide next rotation
        }

        // Fine scan finished
        if (!qwpImproved) {
            return "exit"; // final convergence reached
        }

        // If there was improvement, start next scan for current side
        qwpTestIndex = 0;
        prepareQWPScan(true); // fine scan retry
        return runQWPOptimizationStep();
    }
}
