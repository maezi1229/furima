# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

FURIMA is a Ruby on Rails project cloning the basic look of a flea-market app (Mercari-style). It is currently at a very early scaffold stage: there is one controller (`ItemsController#index`) rendering a static Haml mockup of the homepage, and **no models, migrations, or database schema exist yet** (`db/` only contains `seeds.rb`). Treat any "architecture" here as a starting skeleton, not an established pattern to preserve — when adding features (users, items, purchases, etc.), you are establishing the conventions, not conforming to existing ones.

## Stack

- Ruby 2.5.1, Rails 5.2.4.3 (`Gemfile` / `.ruby-version`)
- MySQL via `mysql2` (`config/database.yml`); databases are `furima_development` / `furima_test` / `furima_production`
- Views: Haml (`haml-rails`), not ERB — new views should be `.html.haml`
- Assets: classic Sprockets asset pipeline (SCSS + CoffeeScript via `sass-rails`/`coffee-rails`), **not** Webpacker — `package.json` has no dependencies and there is no `node_modules`/yarn build step in use
- App server: Puma in development, Unicorn in production (`config/unicorn.rb`, `config/puma.rb`)
- Deployment: Capistrano (`Capfile`, `config/deploy.rb`, `config/deploy/{production,staging}.rb`) targeting a single EC2 host over SSH with rbenv + Unicorn

## Common commands

```bash
bundle install                 # install gems
bin/rails db:setup             # create + seed dev & test DBs (needs a local MySQL with root/no-password on /tmp/mysql.sock, per config/database.yml)
bin/rails server                # run the app (default: http://localhost:3000)
bin/rails console               # REPL
bin/rails test                  # run the full test suite (Minitest, Rails default)
bin/rails test test/controllers/items_controller_test.rb   # run a single test file
bin/rails test test/controllers/items_controller_test.rb:5 # run a single test by line number
bin/rails routes                # inspect current routes
```

There is no RuboCop config, no CI workflow (`.github/`), and no JS/asset build step to run separately — Sprockets compiles assets on the fly in development.

## Known inconsistency to be aware of

`test/controllers/items_controller_test.rb` calls `items_index_url`, which is the route helper Rails scaffolding generates for a `get 'items/index'` route. The actual `config/routes.rb` only defines `root 'items#index'` (no `items_index` route exists), so this test will fail as-is until either the route is restored or the test is updated to use `root_url`. Don't assume the test suite is green — check before relying on it.

## Architecture notes

- `config/routes.rb` currently defines only `root 'items#index'`. As routes are added, this file is the single source of truth for URL structure.
- `ApplicationController` (`app/controllers/application_controller.rb`) gates the app behind HTTP Basic Auth **only in production** (`before_action :basic_auth, if: :production?`), reading credentials from `Rails.application.credentials[:basic_auth][:user/:pass]`. This requires `config/master.key` (gitignored, not in the repo) to decrypt `config/credentials.yml.enc` — production/staging deploys need that key provisioned separately (Capistrano's `deploy:upload` task pushes it to `shared/config/master.key`).
- The homepage view (`app/views/items/index.html.haml`) is a static mockup: category lists, "pickup" product grids, and image URLs are all hardcoded (including some pointing at an external `mercarimaster` S3 bucket from the reference design). None of this is backed by real models yet — building out `Item`/`User`/etc. models and wiring this view to real data is the natural next step for this codebase.
- Per-controller asset files follow Rails convention: `app/assets/stylesheets/<controller>.scss` and `app/assets/javascripts/<controller>.coffee` are generated alongside each controller and auto-included via `application.css`/`application.js` (`require_tree .`).
