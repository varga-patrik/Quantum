#pragma once
#include <string>
#include <vector>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <filesystem>
#include <sstream>
#include <iomanip>
#include "fs_util.h"
#include "KinesisUtil.h"
#include "Correlator.h"

enum class OrchestratorStep {
    HomeAll,
    Setup,
    MeasureFullPhase,
    ReadData,
    AnalyzeData,
    RotateToMinVis,
    AdjustQWP,
    MeasureWithQWP,
    AnalyzeQWPData,
    ProcessQWPResults,
    CheckConvergence,
    Exit
};

enum class MeasurementType {
    FullPhase,
    FineScan
};

const std::string FULL_PHASE_DURATION = "30";
const std::string FINE_SCAN_DURATION = "5";
const double FULL_PHASE_ROTATION_SPEED = 180.0 / 30;  // 6.0 deg/sec
const double FINE_SCAN_ROTATION_SPEED = 20.0 / 5.0;     // 4.0 deg/sec (±10° range)

class Orchestrator {
private:
    // Instruments
    FSUtil& fs;
    KinesisUtil& lambda2_client;
    double lambda2_server;
    KinesisUtil& lambda4_client;
    double lambda4_server;
    Correlator& correlator;

    // State tracking
    OrchestratorStep currentStep;
    std::string dataFolder;

    // Measurement parameters
    double degreeStep;                          // Bin size in degrees (e.g., 5°)
    size_t numAngleBins;                        // Number of bins (e.g., 36 for 180°/5°)
    MeasurementType lastMeasurementType;        // What kind of measurement we just did
    std::string lastMeasurementStartTime;       // GPS time string when measurement started
    int64_t lastMeasurementStartTimePico;       // Converted to picoseconds
    
    // Analysis results
    std::vector<uint64_t> coincidenceBins;      // Coincidence counts per angle bin
    uint64_t totalCoincidences;                 // Total coincidences found
    int64_t stationTimeOffset;                  // Time offset between stations (picoseconds)
    
    // Visibility tracking
    double currentVisibility;                   // Most recent visibility measurement
    double previousVisibility;                  // Previous full-phase visibility
    double visibilityThreshold;                 // Minimum change to continue optimizing
    
    // QWP optimization state
    int qwpSideIndex;                           // 0 = client (bme4), 1 = server (wigner4)
    double qwpCurrentAngle[2];                  // Current angles for [client, server]
    int qwpPhase;                               // 0 = coarse scan, 1 = fine scan
    int qwpTestIndex;                           // Current index in qwpTestAngles
    std::vector<double> qwpTestAngles;          // Angles to test in current scan
    std::vector<double> qwpTestVisibilities;    // Visibility for each tested angle
    double qwpBestVisibility;                   // Best visibility found in current scan
    double qwpBestAngle;                        // Angle that gave best visibility
    bool qwpImprovedLastScan;                   // Whether last scan improved visibility
    
    // QWP scan parameters
    const double QWP_COARSE_STEP = 2.0;         // Coarse scan step size (degrees)
    const double QWP_COARSE_RANGE = 10.0;       // Coarse scan range (±degrees)
    const double QWP_FINE_STEP = 0.5;           // Fine scan step size (degrees)
    const double QWP_FINE_RANGE = 2.0;          // Fine scan range (±degrees)
    const double QWP_MIN_IMPROVEMENT = 0.001;   // Minimum visibility improvement to continue

public:
    Orchestrator(
        FSUtil& fsu,
        KinesisUtil& l2c,
        double l2s,
        KinesisUtil& l4c,
        double l4s,
        Correlator& corr,
        const std::string& dataFolderPath,
        double stepDeg
    );

    // Main control loop - called repeatedly by TCP client
    std::string runNextStep();
    
    // Getters for status monitoring
    double getCurrentVisibility() const { return currentVisibility; }
    OrchestratorStep getCurrentStep() const { return currentStep; }
    const std::vector<uint64_t>& getCoincidenceBins() const { return coincidenceBins; }

private:
    // Step implementations
    std::string stepHomeAll();
    std::string stepSetup();
    std::string stepMeasureFullPhase();
    std::string stepReadData();
    std::string stepAnalyzeData();
    std::string stepFindMinVisibility();
    std::string stepRotateToMinVis();
    std::string stepAdjustQWP();
    std::string stepMeasureWithQWP();
    std::string stepAnalyzeQWPData();
    std::string stepProcessQWPResults();
    std::string stepCheckConvergence();
    
    // Data analysis helpers
    void analyzeCoincidences();
    std::vector<std::string> collectDataFiles(const std::string& condition);
    std::vector<int64_t> loadTimestampsFromFile(const std::filesystem::path& filepath);
    void binCoincidencesByAngle(
        const std::vector<int64_t>& coincidenceTimestamps,
        double rotationSpeed
    );
    std::vector<int64_t> findCoincidences(
        const std::vector<int64_t>& clientTimestamps,
        const std::vector<int64_t>& serverTimestamps,
        int64_t tolerancePico
    );
    
    // Visibility and optimization
    double computeVisibility() const;
    void prepareQWPScan(bool fine);
    std::string runQWPOptimizationStep();
    std::string rotateToMinVis();
    bool hasConverged();
    bool isCurrentSideOptimized() 
    {
        return (qwpPhase == 1 && qwpImproved == false);
    }

    bool areBothSidesOptimized() 
    {
        if (qwpOptSideIndex == 1 && isCurrentSideOptimized())
            return true;

        return false;
    }

};
