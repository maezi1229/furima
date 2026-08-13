# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`furima` (フリマ, "flea market") is a Ruby on Rails 5.2 application scaffolding a Mercari-style flea-market marketplace. The codebase is at a very early stage: the only wired-up feature is a static top page (`items#index`) rendering a hardcoded Haml mockup (search bar, category list, "pickup" product cards) with no backing models, migrations, or database schema yet. There is no `db/migrate` directory and no `db/schema.rb` — the database has not been designed. Expect to be adding the domain models (users, items, categories, purchases, etc.) essentially from scratch.

## Stack

- Ruby 2.5.1 (see `.ruby-version`), Rails 5.2.3 (Gemfile) / 5.2.4.3 (Gemfile.lock)
- MySQL via `mysql2` gem
- Haml for views (`haml-rails`), SCSS for stylesheets, CoffeeScript for JS (Sprockets asset pipeline, not Webpacker)
- Puma in development, Unicorn in production
- Minitest + Capybara/Selenium for system tests (not RSpec)
- Deployment via Capistrano (`capistrano-rails`, `capistrano-rbenv`, `capistrano3-unicorn`) to a server over SSH

## Common commands

Setup:
```
bin/setup                 # bundle install, db setup, clear logs (see bin/setup)
bundle install
```

Database (requires a local MySQL server; credentials in `config/database.yml`, database names `furima_development` / `furima_test`):
```
bin/rails db:create
bin/rails db:migrate
bin/rails db:seed          # runs db/seeds.rb
```

Run the app:
```
bin/rails server            # Puma, http://localhost:3000
```

Console:
```
bin/rails console
```

Tests (Minitest, run through Rake/Rails, not RSpec):
```
bin/rails test                          # full suite
bin/rails test test/controllers/items_controller_test.rb
bin/rails test test/controllers/items_controller_test.rb:5   # single test by line number
bin/rails test:system                   # Capybara/Selenium system tests
```

Deploy (Capistrano — do not run without explicit instruction, as this touches a real remote server defined in `config/deploy/{production,staging}.rb`):
```
bundle exec cap production deploy
bundle exec cap staging deploy
```

There is no JS package manager setup in use (`package.json` has no dependencies); do not assume Yarn/Webpacker tooling.

## Architecture notes

- Standard Rails MVC layout under `app/`. Routes are defined in `config/routes.rb`; currently only `root 'items#index'` is registered.
- `ItemsController#index` (`app/controllers/items_controller.rb`) is presently an empty action — all page content is currently static markup baked directly into `app/views/items/index.html.haml`, including a mockup of `/products/:id` links to product pages that do not yet exist as routes or controllers. When implementing real listing functionality, this view will need to be broken up into partials and driven by real data instead of hardcoded Haml.
- Views use Haml, not ERB. New views/partials should follow the `.html.haml` convention already established in `app/views/layouts` and `app/views/items`.
- Assets follow the classic Sprockets convention: per-controller SCSS/CoffeeScript files (e.g. `app/assets/stylesheets/items.scss`, `app/assets/javascripts/items.coffee`) are auto-included via `require_tree .` in `app/assets/stylesheets/application.css` and `app/assets/javascripts/application.js`. Follow this per-controller file pattern for new controllers rather than adding to the manifest files directly.
- `config/credentials.yml.enc` exists but `config/master.key` is not checked in (gitignored) — encrypted credentials cannot be decrypted without that key being provided out-of-band.
- Production config (`config/environments/production.rb`, `config/unicorn.rb`, `config/deploy.rb`) assumes deployment to a server with rbenv, Unicorn, and a `config/master.key` uploaded via the Capistrano `deploy:upload` task.
