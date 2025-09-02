# DexWebsite

A modern, responsive website built with plain HTML and CSS. This website features a clean design, smooth animations, and is fully responsive across all devices.

## Features

- 🎨 **Modern Design**: Clean, professional layout with beautiful gradients
- 📱 **Responsive**: Works perfectly on mobile, tablet, and desktop
- ⚡ **Fast Loading**: Built with plain HTML/CSS for optimal performance
- 🔧 **Easy Customization**: Well-structured code that's simple to modify
- 🌈 **Smooth Animations**: Hover effects and transitions for better UX

## Getting Started

### Option 1: Direct HTML (Recommended for simple use)

1. Simply open `index.html` in any web browser
2. The website will load immediately with all styling included
3. No server setup required

### Option 2: Jekyll (For advanced features)

1. Install Jekyll: `gem install jekyll bundler`
2. Install dependencies: `bundle install`
3. Run locally: `bundle exec jekyll serve`
4. Visit `http://localhost:4000`

## File Structure

```
dexwebsite/
├── index.html          # Main website file
├── _config.yml         # Jekyll configuration
├── _data/
│   └── main_info.yaml  # Website data and content
└── README.md           # This file
```

## Customization

### Changing Content

Edit the content directly in `index.html` or modify the data in `_data/main_info.yaml` for Jekyll integration.

### Styling

All CSS is included in the `<style>` section of `index.html`. You can:

- Change colors by modifying the CSS variables
- Adjust spacing by changing padding/margin values
- Modify fonts by updating the `font-family` properties
- Add new sections by copying the existing structure

### Key CSS Classes

- `.container`: Main content wrapper
- `.main-content`: White content area
- `.section`: Individual content sections
- `.feature-card`: Feature display cards
- `.cta-button`: Call-to-action buttons

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)
- Internet Explorer 11+

## Performance

This website is optimized for performance:
- No external dependencies
- Minimal CSS
- Optimized images (when added)
- Fast loading times

## Deployment

### GitHub Pages

1. Push your code to a GitHub repository
2. Enable GitHub Pages in repository settings
3. Your site will be available at `https://username.github.io/repository-name`

### Netlify

1. Connect your GitHub repository to Netlify
2. Deploy automatically on every push
3. Get a custom domain and SSL certificate

### Traditional Hosting

Upload all files to your web hosting provider's public directory.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

If you need help or have questions:
- Create an issue in the repository
- Check the documentation
- Review the code examples

---

Built with ❤️ for modern web development 
