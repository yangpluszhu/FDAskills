#!/usr/bin/env node

/**
 * FDA Guidance Document Downloader
 * 
 * This script automates downloading FDA guidance documents with multiple filter options:
 * - Product: Filter by product type
 * - FDA Organization: Filter by FDA organizational unit
 * - Topic: Filter by topic/subject
 * 
 * It handles pagination automatically to ensure all documents are downloaded.
 * 
 * Usage:
 *   node download_fda_by_topic.js --topic "Topic Name"
 *   node download_fda_by_topic.js --product "Product Name"
 *   node download_fda_by_topic.js --organization "Organization Name"
 *   node download_fda_by_topic.js --topic "Topic" --product "Product"
 *   node download_fda_by_topic.js  (interactive mode)
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const readline = require('readline');

// Get download directory (current working directory)
const DOWNLOAD_DIR = process.cwd();

// Ensure download directory exists
if (!fs.existsSync(DOWNLOAD_DIR)) {
    fs.mkdirSync(DOWNLOAD_DIR, { recursive: true });
}

// Create readline interface for interactive mode
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

// Filter configuration - FIXED: organization selector updated from 'organization' to 'org'
const FILTER_CONFIG = {
    product: {
        id: 'lcds-datatable-filter--product',
        name: 'Product',
        selector: '#lcds-datatable-filter--product'
    },
    organization: {
        id: 'lcds-datatable-filter--org',
        name: 'FDA Organization',
        selector: '#lcds-datatable-filter--org'
    },
    topic: {
        id: 'lcds-datatable-filter--topic',
        name: 'Topic',
        selector: '#lcds-datatable-filter--topic'
    }
};

/**
 * Sanitize filename for Windows compatibility
 */
function sanitizeFilename(title, index) {
    let safeName = title
        .replace(/[<>:"/\\|?*]/g, '_')
        .replace(/\s+/g, '_')
        .substring(0, 100);
    return `${index}_${safeName}.pdf`;
}

/**
 * Find option from dropdown options (case-insensitive partial match)
 */
function findOption(options, query) {
    const lowerQuery = query.toLowerCase();
    return options.find(opt => 
        opt.text.toLowerCase().includes(lowerQuery)
    );
}

/**
 * Ask question in interactive mode
 */
function askQuestion(question) {
    return new Promise(resolve => {
        rl.question(question, answer => {
            resolve(answer.trim());
        });
    });
}

/**
 * Apply a single filter
 */
async function applyFilter(page, filterType, filterValue) {
    const config = FILTER_CONFIG[filterType];
    if (!config) {
        throw new Error(`Unknown filter type: ${filterType}`);
    }

    console.log(`\n🔍 Setting ${config.name} filter: ${filterValue}...`);

    await page.waitForSelector(config.selector, { timeout: 20000 });
    const dropdown = await page.$(config.selector);

    if (!dropdown) {
        throw new Error(`Cannot find ${config.name} filter dropdown`);
    }

    const options = await dropdown.evaluate(el => {
        return Array.from(el.options).map(opt => ({
            value: opt.value,
            text: opt.text.trim()
        }));
    });

    console.log(`📋 Available ${config.name} options: ${options.length}`);

    const matchedOption = findOption(options, filterValue);

    if (!matchedOption) {
        console.log(`\n⚠️ No matching ${config.name} found. Available options:`);
        options.forEach(opt => console.log(`  - ${opt.text}`));
        throw new Error(`${config.name} not found: ${filterValue}`);
    }

    console.log(`✅ Found ${config.name} option: ${matchedOption.text}`);

    // Apply filter using native JavaScript to trigger change event
    await page.evaluate(({ selector, value }) => {
        const select = document.querySelector(selector);
        if (select) {
            select.value = value;
            const event = new Event('change', { bubbles: true });
            select.dispatchEvent(event);
        }
    }, { selector: config.selector, value: matchedOption.value });

    console.log(`✅ ${config.name} filter applied`);
    await page.waitForTimeout(3000);

    // Wait for DataTables processing to complete
    await page.waitForFunction(() => {
        const processing = document.querySelector('.dataTables_processing');
        return !processing || processing.style.display === 'none';
    }, { timeout: 30000 });

    console.log(`✅ ${config.name} table data updated`);

    return matchedOption.text;
}

/**
 * Main download function
 */
async function downloadFDA(filters) {
    console.log('🚀 Starting FDA Guidance Document Downloader...\n');
    
    // Display active filters
    const activeFilters = Object.entries(filters)
        .filter(([_, value]) => value)
        .map(([type, value]) => `${FILTER_CONFIG[type].name}: ${value}`);
    
    if (activeFilters.length === 0) {
        console.log('⚠️ No filters specified, will download all documents');
    } else {
        console.log('📋 Active filters:');
        activeFilters.forEach(f => console.log(`  - ${f}`));
    }
    console.log('');
    
    const browser = await chromium.launch({ headless: false });
    const page = await browser.newPage();
    
    const allDocuments = [];
    const appliedFilters = {};
    
    try {
        // Visit FDA search page
        const searchUrl = 'https://www.fda.gov/regulatory-information/search-fda-guidance-documents';
        console.log(`📍 Visiting URL: ${searchUrl}`);
        
        await page.goto(searchUrl, {
            waitUntil: 'domcontentloaded',
            timeout: 120000
        });
        
        console.log('✅ Page base content loaded');
        await page.waitForTimeout(15000);  // Increased wait time for filters to fully load
        
        // Apply filters in order: Product -> FDA Organization -> Topic
        const filterOrder = ['product', 'organization', 'topic'];
        
        for (const filterType of filterOrder) {
            if (filters[filterType]) {
                try {
                    const appliedValue = await applyFilter(page, filterType, filters[filterType]);
                    appliedFilters[filterType] = appliedValue;
                } catch (error) {
                    console.error(`\n❌ Failed to apply ${FILTER_CONFIG[filterType].name} filter:`, error.message);
                    throw error;
                }
            }
        }
        
        // Save screenshot
        const filterParts = Object.entries(appliedFilters)
            .map(([type, value]) => `${type}_${value.replace(/[^a-zA-Z0-9]/g, '_')}`)
            .join('_');
        const safeFilename = filterParts || 'all';
        
        await page.screenshot({ 
            path: path.join(DOWNLOAD_DIR, `page_${safeFilename}_filtered.png`), 
            fullPage: true 
        });
        console.log('✅ Page screenshot saved\n');
        
        // Pagination handling
        console.log('📊 Starting pagination...');
        
        let pageNum = 1;
        let hasMorePages = true;
        
        while (hasMorePages) {
            console.log(`\n📄 Processing page ${pageNum}...`);
            
            // Extract documents from current page
            const documents = await page.evaluate((currentPageNum) => {
                const docs = [];
                const rows = document.querySelectorAll('#DataTables_Table_0 tbody tr');
                
                rows.forEach((row) => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length >= 2) {
                        const titleCell = cells[0];
                        const titleLink = titleCell.querySelector('a');
                        const title = titleLink ? titleLink.textContent.trim() : titleCell.textContent.trim();
                        
                        const pdfCell = cells[1];
                        const pdfLink = pdfCell ? pdfCell.querySelector('a[href*="/media/"]') : null;
                        const pdfUrl = pdfLink ? pdfLink.getAttribute('href') : null;
                        
                        const productCell = cells[2];
                        const product = productCell ? productCell.textContent.trim() : '';
                        
                        const organizationCell = cells[3];
                        const organization = organizationCell ? organizationCell.textContent.trim() : '';
                        
                        const topicCell = cells[4];
                        const topic = topicCell ? topicCell.textContent.trim() : '';
                        
                        if (pdfUrl && title) {
                            docs.push({
                                title: title,
                                pdfUrl: pdfUrl,
                                product: product,
                                organization: organization,
                                topic: topic,
                                page: currentPageNum
                            });
                        }
                    }
                });
                
                return docs;
            }, pageNum);
            
            console.log(`   Found ${documents.length} documents`);
            allDocuments.push(...documents);
            
            // Check for next page
            const hasNextPage = await page.evaluate(() => {
                const nextButton = document.querySelector('#DataTables_Table_0_next');
                if (nextButton) {
                    return !nextButton.classList.contains('disabled');
                }
                return false;
            });
            
            if (hasNextPage) {
                console.log('   ➡️  Clicking next page...');
                
                await page.evaluate(() => {
                    const nextButton = document.querySelector('#DataTables_Table_0_next');
                    if (nextButton) {
                        nextButton.click();
                    }
                });
                
                await page.waitForTimeout(3000);
                
                // Wait for DataTables processing
                await page.waitForFunction(() => {
                    const processing = document.querySelector('.dataTables_processing');
                    return !processing || processing.style.display === 'none';
                }, { timeout: 30000 });
                
                pageNum++;
            } else {
                console.log('   ✅ Reached last page');
                hasMorePages = false;
            }
        }
        
        console.log(`\n📊 Total ${allDocuments.length} PDF documents found\n`);
        
        if (allDocuments.length === 0) {
            console.log('⚠️ No documents found');
            return;
        }
        
        // Display found documents
        console.log('📄 Document list:');
        allDocuments.forEach((doc, i) => {
            console.log(`  ${i + 1}. [Page ${doc.page}] ${doc.title}`);
            if (doc.product) console.log(`     Product: ${doc.product}`);
            if (doc.organization) console.log(`     Organization: ${doc.organization}`);
            if (doc.topic) console.log(`     Topic: ${doc.topic}`);
        });
        
        // Save document list
        const docList = allDocuments.map((doc, i) => ({
            index: i + 1,
            title: doc.title,
            product: doc.product,
            organization: doc.organization,
            topic: doc.topic,
            pdfUrl: doc.pdfUrl,
            page: doc.page,
            filename: sanitizeFilename(doc.title, i + 1)
        }));
        
        const listFilename = `${safeFilename}_all_documents_list.json`;
        fs.writeFileSync(
            path.join(DOWNLOAD_DIR, listFilename), 
            JSON.stringify(docList, null, 2)
        );
        console.log(`\n✅ Document list saved to ${listFilename}`);
        
        // Download all PDFs
        console.log('\n⬇️ Starting PDF download...\n');
        
        let successCount = 0;
        let skipCount = 0;
        let failCount = 0;
        
        for (let i = 0; i < allDocuments.length; i++) {
            const doc = allDocuments[i];
            const filename = sanitizeFilename(doc.title, i + 1);
            const filepath = path.join(DOWNLOAD_DIR, filename);
            
            // Check if file already exists
            if (fs.existsSync(filepath)) {
                const stats = fs.statSync(filepath);
                if (stats.size > 0) {
                    console.log(`[${i + 1}/${allDocuments.length}] ⏭️  File already exists: ${filename}`);
                    skipCount++;
                    continue;
                }
            }
            
            console.log(`[${i + 1}/${allDocuments.length}] ${doc.title}`);
            
            try {
                const fullUrl = doc.pdfUrl.startsWith('http') 
                    ? doc.pdfUrl 
                    : `https://www.fda.gov${doc.pdfUrl}`;
                console.log(`   📥 Downloading: ${fullUrl}`);
                
                // Download using browser fetch API
                const downloadResult = await page.evaluate(async (url) => {
                    try {
                        const response = await fetch(url, {
                            method: 'GET',
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/pdf,*/*',
                                'Accept-Language': 'en-US,en;q=0.9',
                                'Referer': 'https://www.fda.gov/'
                            }
                        });
                        
                        if (!response.ok) {
                            return { success: false, error: `HTTP ${response.status}` };
                        }
                        
                        const blob = await response.blob();
                        const arrayBuffer = await blob.arrayBuffer();
                        const uint8Array = new Uint8Array(arrayBuffer);
                        
                        return { 
                            success: true, 
                            data: Array.from(uint8Array),
                            size: uint8Array.length
                        };
                    } catch (error) {
                        return { success: false, error: error.message };
                    }
                }, fullUrl);
                
                if (downloadResult.success) {
                    const buffer = Buffer.from(downloadResult.data);
                    fs.writeFileSync(filepath, buffer);
                    console.log(`   ✅ Downloaded: ${filename} (${(downloadResult.size / 1024).toFixed(2)} KB)`);
                    successCount++;
                } else {
                    console.log(`   ❌ Download failed: ${downloadResult.error}`);
                    failCount++;
                }
                
            } catch (error) {
                console.log(`   ❌ Download failed: ${error.message}`);
                failCount++;
            }
            
            // Add delay between downloads
            await page.waitForTimeout(2000);
        }
        
        // Print summary
        console.log('\n' + '='.repeat(60));
        console.log('📊 Download Statistics:');
        console.log(`  ✅ Successfully downloaded: ${successCount}`);
        console.log(`  ⏭️  Skipped (already exist): ${skipCount}`);
        console.log(`  ❌ Failed: ${failCount}`);
        console.log(`  📁 Saved to: ${DOWNLOAD_DIR}`);
        console.log('='.repeat(60));
        
        // Verify downloads
        console.log('\n🔍 Verifying downloads...');
        let allValid = true;
        for (let i = 0; i < allDocuments.length; i++) {
            const doc = allDocuments[i];
            const filename = sanitizeFilename(doc.title, i + 1);
            const filepath = path.join(DOWNLOAD_DIR, filename);
            
            if (fs.existsSync(filepath)) {
                const stats = fs.statSync(filepath);
                if (stats.size === 0) {
                    console.log(`  ⚠️  File size is 0: ${filename}`);
                    allValid = false;
                }
            } else {
                console.log(`  ❌ File not found: ${filename}`);
                allValid = false;
            }
        }
        
        if (allValid) {
            console.log('\n✅ All documents downloaded successfully and complete!');
        }
        
    } catch (error) {
        console.error('\n❌ Error occurred:', error.message);
        console.error(error.stack);
    } finally {
        await browser.close();
        console.log('\n👋 Browser closed');
    }
}

/**
 * Parse command line arguments
 */
function parseArguments() {
    const args = process.argv.slice(2);
    const filters = {
        product: null,
        organization: null,
        topic: null
    };

    for (let i = 0; i < args.length; i++) {
        const arg = args[i];
        const nextArg = args[i + 1];

        switch (arg) {
            case '--product':
            case '-p':
                if (nextArg && !nextArg.startsWith('--')) {
                    filters.product = nextArg;
                    i++;
                }
                break;
            case '--organization':
            case '-o':
                if (nextArg && !nextArg.startsWith('--')) {
                    filters.organization = nextArg;
                    i++;
                }
                break;
            case '--topic':
            case '-t':
                if (nextArg && !nextArg.startsWith('--')) {
                    filters.topic = nextArg;
                    i++;
                }
                break;
            case '--help':
            case '-h':
                showHelp();
                process.exit(0);
                break;
        }
    }

    return filters;
}

/**
 * Show help message
 */
function showHelp() {
    console.log(`
FDA Guidance Document Downloader

Usage:
  node download_fda_by_topic.js [options]

Options:
  -p, --product <name>       Filter by Product
  -o, --organization <name>  Filter by FDA Organization
  -t, --topic <name>         Filter by Topic
  -h, --help                 Show this help message

Examples:
  # Download by Topic only
  node download_fda_by_topic.js --topic "Good Clinical Practice (GCP)"

  # Download by Product only
  node download_fda_by_topic.js --product "Drugs"

  # Download by FDA Organization
  node download_fda_by_topic.js --organization "CDER"

  # Combine multiple filters
  node download_fda_by_topic.js --topic "GCP" --product "Drugs" --organization "CDER"

  # Interactive mode (lists all available options)
  node download_fda_by_topic.js
`);
}

/**
 * List all available filter options
 */
async function listAllFilterOptions() {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    
    try {
        // Visit FDA search page
        const searchUrl = 'https://www.fda.gov/regulatory-information/search-fda-guidance-documents';
        console.log(`📍 Visiting URL: ${searchUrl}`);
        
        await page.goto(searchUrl, {
            waitUntil: 'domcontentloaded',
            timeout: 120000
        });
        
        console.log('✅ Page base content loaded');
        await page.waitForTimeout(15000);  // Increased wait time for filters to fully load

        // Get all filter options
        for (const [filterType, config] of Object.entries(FILTER_CONFIG)) {
            console.log(`\n📋 Getting ${config.name} options...`);
            
            try {
                await page.waitForSelector(config.selector, { timeout: 20000 });
                const dropdown = await page.$(config.selector);
                
                if (!dropdown) {
                    console.log(`  ⚠️ Cannot find ${config.name} filter`);
                    continue;
                }
                
                const options = await dropdown.evaluate(el => {
                    return Array.from(el.options).map(opt => ({
                        value: opt.value,
                        text: opt.text.trim()
                    }));
                });
                
                console.log(`\n✅ ${config.name} options (${options.length}):`);
                options.forEach((opt, index) => {
                    console.log(`  ${index + 1}. ${opt.text}`);
                });
            } catch (error) {
                console.log(`  ❌ Failed to get ${config.name} options: ${error.message}`);
            }
        }
        
    } catch (error) {
        console.error('❌ Failed to get filter options:', error.message);
    } finally {
        await browser.close();
        console.log('\n👋 Browser closed');
    }
}

/**
 * Main entry point
 */
async function main() {
    const filters = parseArguments();
    
    // Check if any filter is provided
    const hasFilters = Object.values(filters).some(v => v !== null);
    
    // Interactive mode if no arguments provided
    if (!hasFilters) {
        console.log('🎯 FDA Guidance Document Downloader');
        console.log('====================\n');
        console.log('Supported filters:');
        console.log('  --product, -p       Product');
        console.log('  --organization, -o  FDA Organization');
        console.log('  --topic, -t         Topic\n');
        console.log('Examples:');
        console.log('  node download_fda_by_topic.js --topic "GCP"');
        console.log('  node download_fda_by_topic.js --product "Drugs" --organization "CDER"\n');
        
        // Automatically get and list all available options
        console.log('🔍 Getting all available filter options...');
        await listAllFilterOptions();
        rl.close();
        process.exit(0);
    }
    
    rl.close();
    
    try {
        await downloadFDA(filters);
    } catch (error) {
        console.error('❌ Execution failed:', error.message);
        process.exit(1);
    }
}

// Run main function
main();
