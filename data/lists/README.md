# Public Sanctions & PEP Reference Lists

For development and coursework demonstrations, OnboardIQ comes with a synthetic sample list:
- `sanctions_sample.csv`
- `pep_sample.csv`

## Official Public Source Downloads (For Full Evaluation)

To run against the complete real public sanctions lists during evaluation:

### 1. US OFAC SDN List (Specially Designated Nationals)
- **Source**: U.S. Department of the Treasury
- **URL**: https://www.treasury.gov/ofac/downloads/sdn.csv
- **Format**: CSV / XML
- Place in `data/lists/ofac_sdn.csv`

### 2. United Nations Consolidated Sanctions List
- **Source**: United Nations Security Council
- **URL**: https://www.un.org/securitycouncil/content/un-sc-consolidated-list
- **Format**: XML / CSV
- Place in `data/lists/un_consolidated.csv`

### 3. OpenSanctions / PEP dataset
- **Source**: OpenSanctions project
- **URL**: https://data.opensanctions.org/datasets/latest/default/entities.ftm.json
- **License**: Non-commercial / CC-BY-SA

> Note: Never use real customer data. Only official government public designation lists are used for screening targets.

