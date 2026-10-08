-- TrustRail Postgres init: creates two databases per spec Section 1.1
-- Gateway and Market use separate databases on one Postgres instance,
-- with no cross-database joins.

CREATE DATABASE gateway_db;
CREATE DATABASE market_db;
