---
name: fdaGuide
description: Automate downloading FDA guidance documents with multiple filter support including Product, FDA Organization, and Topic. Use when user wants to download FDA guidance PDFs using one or more filters. The skill handles pagination automatically to ensure no documents are missed.
---

# FDA Guide Document Downloader

This skill automates the download of FDA guidance documents from the FDA Guidance Documents search page with support for multiple filters:
- **Product** - Filter by product type (e.g., Drugs, Devices, Biologics)
- **FDA Organization** - Filter by FDA organizational unit (e.g., CDER, CDRH, CBER)
- **Topic** - Filter by topic/subject (e.g., Good Clinical Practice, Postmarket)

## When to Use

Use this skill when the user wants to:
- Download FDA guidance documents filtered by Product, FDA Organization, Topic, or any combination
- Automatically handle pagination to download all documents across multiple pages
- Save PDF documents to the current working directory
- Verify document integrity and relevance

## Prerequisites

- Node.js installed
- Playwright installed (`npm install playwright`)
- Chromium browser available

## Usage

### Command Line Options

```bash
node scripts/download_fda_by_topic.js [options]
```

**Available Options:**
- `-p, --product <name>` - Filter by Product
- `-o, --organization <name>` - Filter by FDA Organization
- `-t, --topic <name>` - Filter by Topic
- `-h, --help` - Show help message

### Usage Examples

#### Filter by Topic only
```bash
node scripts/download_fda_by_topic.js --topic "Good Clinical Practice (GCP)"
```

#### Filter by Product only
```bash
node scripts/download_fda_by_topic.js --product "Drugs"
```

#### Filter by FDA Organization only
```bash
node scripts/download_fda_by_topic.js --organization "CDER"
```

#### Combine multiple filters
```bash
node scripts/download_fda_by_topic.js --topic "GCP" --product "Drugs" --organization "CDER"
```

#### Interactive Mode (lists all available options)
```bash
node scripts/download_fda_by_topic.js
```

## How It Works

1. **Navigate to FDA Search Page**: Opens `https://www.fda.gov/regulatory-information/search-fda-guidance-documents`

2. **Apply Filters**: 
   - Filters are applied in order: Product → FDA Organization → Topic
   - Each filter uses case-insensitive partial matching
   - The table updates automatically after each filter is applied

3. **Pagination Handling**:
   - Extracts documents from the current page
   - Checks for the "Next" button (`#DataTables_Table_0_next`)
   - Continues to next page until all pages are processed
   - Tracks page numbers for document organization

4. **Document Extraction**:
   - Extracts document title from the first column
   - Extracts PDF URL from the second column (links containing `/media/`)
   - Extracts Product from the third column
   - Extracts FDA Organization from the fourth column
   - Extracts Topic from the fifth column
   - Stores metadata including page number for traceability

5. **PDF Download**:
   - Uses browser's fetch API within page context to avoid abuse detection
   - Downloads each PDF with proper headers and credentials
   - Sanitizes filenames for Windows compatibility
   - Saves files with numeric prefix for ordering
   - Adds delay between downloads to be respectful to the server

6. **Verification**:
   - Verifies all files exist and have non-zero size
   - Generates a JSON manifest with document metadata
   - Saves screenshot of filtered page for reference

## Output

### Downloaded Files
- PDF files saved to current working directory with format: `{index}_{sanitized_title}.pdf`
- Example: `1_Use_of_Real-World_Evidence_to_Support_Regulatory_Decision-Making_for_Medical_Devices.pdf`

### Metadata Files
- `{filters}_all_documents_list.json`: Complete list of all documents with metadata
  - `index`: Document number
  - `title`: Document title
  - `product`: Product classification
  - `organization`: FDA Organization
  - `topic`: Topic classification
  - `pdfUrl`: Download URL
  - `page`: Page number where document was found
  - `filename`: Saved filename

- `page_{filters}_filtered.png`: Screenshot of the filtered search page

## Script Reference

### `scripts/download_fda_by_topic.js`

Main automation script using Playwright.

**Features:**
- Headless browser automation
- Multiple filter support (Product, FDA Organization, Topic)
- Automatic pagination handling
- Progress logging with emojis
- Error handling and recovery
- File integrity verification
- Duplicate detection (skips existing files)

**Key Functions:**
- `parseArguments()`: Parses command line arguments for filters
- `applyFilter(page, filterType, filterValue)`: Applies a single filter
- `sanitizeFilename(title, index)`: Creates Windows-safe filenames
- `findOption(options, query)`: Case-insensitive option matching
- `downloadFDA(filters)`: Main download function with multi-filter support
- `listAllFilterOptions()`: Lists all available filter options

## Common Filter Values

### Common Products
- Drugs
- Devices
- Biologics
- Veterinary Medicine
- Food
- Tobacco
- And more...

### Common FDA Organizations
- CDER (Center for Drug Evaluation and Research)
- CDRH (Center for Devices and Radiological Health)
- CBER (Center for Biologics Evaluation and Research)
- CVM (Center for Veterinary Medicine)
- CFSAN (Center for Food Safety and Applied Nutrition)
- And more...

### Common Topics
- Good Clinical Practice (GCP)
- Real World Data / Real World Evidence (RWD/RWE)
- Postmarket
- Premarket
- Clinical - Medical
- Administrative / Procedural
- And 60+ more topics

## Example Usage Scenarios

### Download GCP Documents for Drugs
```bash
node scripts/download_fda_by_topic.js --topic "Good Clinical Practice (GCP)" --product "Drugs"
```

### Download RWD/RWE Documents from CDER
```bash
node scripts/download_fda_by_topic.js --topic "Real World Data / Real World Evidence (RWD/RWE)" --organization "CDER"
```

### Download All CDER Documents
```bash
node scripts/download_fda_by_topic.js --organization "CDER"
```

### Download Postmarket Documents for Devices
```bash
node scripts/download_fda_by_topic.js --topic "Postmarket" --product "Devices"
```

## Troubleshooting

### Issue: Script cannot find the filter option
- The script performs case-insensitive partial matching
- Try using a shorter, unique portion of the option name
- Run interactive mode to see all available options:
  ```bash
  node scripts/download_fda_by_topic.js
  ```

### Issue: Download fails with abuse detection
- The script uses browser fetch API to avoid this
- If still occurring, increase delay between downloads (modify `page.waitForTimeout` value)

### Issue: Pagination not working
- The script waits for DataTables processing to complete
- If table doesn't update, check internet connection and try again

### Issue: Files not saving
- Ensure current directory has write permissions
- Check disk space availability
- Verify Node.js has permission to write files

## Notes

- The script runs with `headless: false` to allow visual monitoring
- Downloads include a 2-second delay between each file to be respectful
- Existing files are skipped if they have non-zero size
- All documents are verified for integrity after download
- The FDA website structure may change; update selectors if needed
- Multiple filters are combined with AND logic (all filters must match)
