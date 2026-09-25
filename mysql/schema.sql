-- datetime holds UTC values; timezone is visitor geolocation metadata.
CREATE TABLE IF NOT EXISTS logs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ip_address VARCHAR(45) NULL,
    datetime DATETIME(6) NULL,
    request_type TEXT NULL,
    endpoint TEXT NULL,
    http_version TEXT NULL,
    status_code SMALLINT UNSIGNED NULL,
    user_agent TEXT NULL,
    Agent_Type VARCHAR(1) NULL,
    country TEXT NULL,
    countryCode TEXT NULL,
    region TEXT NULL,
    regionName TEXT NULL,
    city TEXT NULL,
    zip TEXT NULL,
    lat DOUBLE NULL,
    lon DOUBLE NULL,
    timezone TEXT NULL,
    INDEX logs_datetime (datetime),
    INDEX logs_agent_datetime (Agent_Type, datetime)
) ENGINE=InnoDB DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin;
