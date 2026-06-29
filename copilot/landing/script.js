/* ═══════════════════════════════════════════════════════════
   ISRO NetOps Predictive Co-Pilot — Advanced Landing Page Scripts
   Three.js Globe, 3D Tilt, Scroll Reveals, Counters
   ═══════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  // ── NAVBAR SCROLL ──
  const navbar = document.getElementById("navbar");
  window.addEventListener("scroll", () => {
    navbar.classList.toggle("scrolled", window.scrollY > 50);
  });

  // ── THREE.JS GLOBE (HERO) ──
  const heroContainer = document.getElementById("heroThree");
  if (heroContainer && typeof THREE !== 'undefined') {
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    heroContainer.appendChild(renderer.domElement);

    // Group for rotation
    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    // 1. Base Sphere (Wireframe)
    const geometry = new THREE.IcosahedronGeometry(10, 4);
    const material = new THREE.MeshBasicMaterial({
      color: 0x00E5FF,
      wireframe: true,
      transparent: true,
      opacity: 0.1
    });
    const sphere = new THREE.Mesh(geometry, material);
    globeGroup.add(sphere);

    // 2. Nodes (Satellites / Ground Stations)
    const nodeCount = 60;
    const nodeGeometry = new THREE.SphereGeometry(0.15, 8, 8);
    const nodes = [];

    const colors = [0x00E5FF, 0x00E5FF, 0x00FF87, 0x00FF87, 0xFF9500, 0xFF3B5C];
    
    for (let i = 0; i < nodeCount; i++) {
      const phi = Math.acos(-1 + (2 * i) / nodeCount);
      const theta = Math.sqrt(nodeCount * Math.PI) * phi;
      
      const r = 10;
      const x = r * Math.cos(theta) * Math.sin(phi);
      const y = r * Math.sin(theta) * Math.sin(phi);
      const z = r * Math.cos(phi);

      const color = colors[Math.floor(Math.random() * colors.length)];
      
      const nodeMaterial = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.8
      });

      const nodeMesh = new THREE.Mesh(nodeGeometry, nodeMaterial);
      nodeMesh.position.set(x, y, z);
      
      // Store original position and pulsing data
      nodes.push({
        mesh: nodeMesh,
        origPos: new THREE.Vector3(x, y, z),
        phase: Math.random() * Math.PI * 2,
        speed: 0.02 + Math.random() * 0.03
      });

      globeGroup.add(nodeMesh);
    }

    // 3. Connecting Lines
    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x00E5FF,
      transparent: true,
      opacity: 0.15
    });

    const lineGeom = new THREE.BufferGeometry();
    const linePositions = [];
    
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dist = nodes[i].origPos.distanceTo(nodes[j].origPos);
        if (dist < 4.5) {
          linePositions.push(
            nodes[i].origPos.x, nodes[i].origPos.y, nodes[i].origPos.z,
            nodes[j].origPos.x, nodes[j].origPos.y, nodes[j].origPos.z
          );
        }
      }
    }
    
    lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
    const lines = new THREE.LineSegments(lineGeom, lineMaterial);
    globeGroup.add(lines);

    camera.position.z = 22;
    camera.position.x = 8;
    camera.position.y = 5;

    // Mouse Interaction
    let targetX = 0;
    let targetY = 0;
    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
      targetX = (event.clientX - windowHalfX) * 0.001;
      targetY = (event.clientY - windowHalfY) * 0.001;
    });

    // Animation Loop
    function animate() {
      requestAnimationFrame(animate);

      // Rotate group
      globeGroup.rotation.y += 0.002;
      globeGroup.rotation.x += (targetY - globeGroup.rotation.x) * 0.05;
      globeGroup.rotation.y += (targetX - globeGroup.rotation.y) * 0.05;

      // Pulse nodes
      const time = Date.now() * 0.001;
      nodes.forEach(n => {
        n.phase += n.speed;
        const scale = 1 + Math.sin(n.phase) * 0.5;
        n.mesh.scale.set(scale, scale, scale);
        
        // Slight hover effect
        n.mesh.position.copy(n.origPos).multiplyScalar(1 + Math.sin(time * 2 + n.phase) * 0.02);
      });

      renderer.render(scene, camera);
    }
    animate();

    // Resize handler
    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
  }

  // ── 3D TILT EFFECT ──
  const tiltElements = document.querySelectorAll('[data-tilt]');
  
  tiltElements.forEach(el => {
    el.addEventListener('mousemove', e => {
      const rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      const xPct = x / rect.width;
      const yPct = y / rect.height;
      
      // Calculate rotation limits (-10 to 10 deg)
      const rotateX = (0.5 - yPct) * 20; 
      const rotateY = (xPct - 0.5) * 20;
      
      el.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
    });
    
    el.addEventListener('mouseleave', () => {
      el.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
      el.style.transition = 'transform 0.5s cubic-bezier(0.2, 0.8, 0.2, 1)';
    });
    
    el.addEventListener('mouseenter', () => {
      el.style.transition = 'none';
    });
  });

  // ── SCROLL REVEAL ──
  const reveals = document.querySelectorAll(".reveal");
  const revealObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        const delay = parseInt(e.target.dataset.delay || "0", 10);
        setTimeout(() => e.target.classList.add("visible"), delay);
        revealObs.unobserve(e.target);
      }
    });
  }, { threshold: 0.15 });
  
  reveals.forEach((el) => revealObs.observe(el));

  // ── ANIMATE COUNTERS & RINGS ──
  function animateMetrics() {
    // Number counters
    document.querySelectorAll(".counter").forEach((el) => {
      if (el.dataset.animated) return;
      el.dataset.animated = "1";
      
      const target = parseFloat(el.dataset.target);
      const suffix = el.dataset.suffix || "";
      const decimals = parseInt(el.dataset.decimals || "0", 10);
      const duration = 2000;
      const start = performance.now();

      function tick(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4); // easeOutQuart
        const current = target * eased;
        el.textContent = current.toFixed(decimals) + suffix;
        if (progress < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });

    // SVG Rings
    document.querySelectorAll('.ring-fill').forEach(ring => {
      const pct = parseFloat(ring.dataset.pct);
      const offset = 326 - (326 * pct / 100);
      setTimeout(() => {
        ring.style.strokeDashoffset = offset;
      }, 200);
    });
  }

  // Also animate hero stats on load
  setTimeout(() => {
    document.querySelectorAll(".stat-value[data-count]").forEach((el) => {
      const target = parseFloat(el.dataset.count);
      const decimals = parseInt(el.dataset.decimals || "0", 10);
      const duration = 1800;
      const start = performance.now();

      function tick(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 4);
        el.textContent = (target * eased).toFixed(decimals);
        if (progress < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }, 600);

  // Trigger metrics on scroll
  const metricsObs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        animateMetrics();
        // Bar charts
        e.target.querySelectorAll(".cb-fill").forEach((bar) => {
          setTimeout(() => {
            bar.style.width = bar.dataset.width + "%";
          }, 300);
        });
      }
    });
  }, { threshold: 0.3 });
  
  document.querySelectorAll(".metrics-grid, .features-chart").forEach((el) => metricsObs.observe(el));

})();
