#pragma once
#include <string>
#include <vector>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <vector>
#include <algorithm>
#include <filesystem>
#include "fs_util.h"
#include "KinesisUtil.h"
#include "Correlator.h"

enum class OrchestratorStep {
    HomeAll,
    Setup,
    MeasureFullPhase,
    ReadData,
    AnalyzeData,
    FindMinVisibility,
    AdjustQWP,
    FineScan,
    CheckImprovement,
    Exit
};

const std::string FullPhaseCollectionTime = "23";
const std::string FinePhaseCollectionTime = "5";

class Orchestrator {
private:
    // Instruments
    FSUtil fs;                       // GPS clock utility
    KinesisUtil lambda2_client;      // Client λ/2 rotator
    double lambda2_server;      // Server λ/2 rotator
    KinesisUtil lambda4_client;      // Client λ/4 rotator
    double lambda4_server;      // Server λ/4 rotator
    Correlator correlator;           // Correlation calculator

    // Internal state
    OrchestratorStep currentStep;                   // Keeps track of current step
    std::string dataFolder;          // Folder containing timestamp data

    // Parameters
    double degreeStep;               // e.g. 5° bins
    std::vector<uint64_t> coincidences;
    double improvementThreshold;

    // For QWP optimization
    int qwpOptSideIndex = 0;           // 0 = client, 1 = server
    double qwpCurrentAngle[2] = {0.0, 0.0};
    double qwpCoarseStep = 2.0;
    double qwpCoarseRange = 10.0;
    double qwpFineStep = 0.5;
    double qwpFineRange = 2.0;
    bool qwpImproved = true;
    int qwpPhase = 0;                  // 0 = coarse scan, 1 = fine scan
    int qwpTestIndex = 0;              // index of current angle in scan
    std::vector<double> qwpTestAngles; // temporary storage for angles to try
    double qwpBestVisibility = 0.0;
    double qwpMinImprovement = 0.001;  // min improvement to accept


public:
    Orchestrator(
        const FSUtil& fsu,
        const KinesisUtil& l2c,
        const double& l2s,
        const KinesisUtil& l4c,
        const double& l4s,
        const Correlator& corr,
        const std::string& dataFolderPath,
        double stepDeg = 5.0
    );

    // Main control
    std::string runNextStep();       // Called by TCP client loop

private:
    // Step actions
    std::string homeAll();

    // Data analysis
    void analyzeData(); // Read, bin, and return coincidences
    void clearDataFolder();              // Delete all old data files
    std::vector<std::string> collectDataFiles(const std::string& condition);
    std::vector<double> loadTimestamps(const std::filesystem::path& filepath);
    std::vector<double> Orchestrator::calculateCoincidences(
        const std::vector<double>& clientTimestamps,
        const std::vector<double>& serverTimestamps,
        double toleranceNs);
    double computeVisibility() const;
    void prepareQWPScan(bool fine);
    std::string runQWPOptimizationStep();
    std::string rotateToMinVis();
    bool hasConverged();
};
