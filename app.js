const areaCoordinates = {
  'quan-1': [10.7769, 106.7009],
  'binh-thanh': [10.8106, 106.7091],
  'thu-duc': [10.8491, 106.7717],
  'quan-7': [10.734, 106.7218],
  'tan-binh': [10.8015, 106.6527],
  'go-vap': [10.8387, 106.6653],
  'tan-phu': [10.7916, 106.6273],
  'nha-be': [10.6961, 106.738],
  'binh-chanh': [10.6876, 106.5946]
};

const projects = [
  { id: 'riverpark', name: 'River Park Thủ Đức', developer: 'Mẫu dữ liệu · East side', area: 'thu-duc', price: 4.2, unit: '2PN · 68–76 m²', rooms: [1, 2], amenities: ['park', 'parking', 'pool', 'transit'], tags: ['Ven sông', 'Metro tương lai'] },
  { id: 'cedar', name: 'Cedar Park Bình Thạnh', developer: 'Mẫu dữ liệu · Inner city', area: 'binh-thanh', price: 6.1, unit: '2PN · 70–82 m²', rooms: [1, 2, 3], amenities: ['school', 'park', 'parking', 'pool'], tags: ['Trung tâm', 'Đủ tiện ích'] },
  { id: 'aqua7', name: 'Aqua Vista Quận 7', developer: 'Mẫu dữ liệu · South side', area: 'quan-7', price: 5.8, unit: '2PN · 72–85 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool', 'quiet'], tags: ['Khu đô thị', 'Không gian xanh'] },
  { id: 'metroline', name: 'Metroline Tân Cảng', developer: 'Mẫu dữ liệu · Riverside', area: 'binh-thanh', price: 7.6, unit: '2PN · 65–78 m²', rooms: [1, 2, 3], amenities: ['parking', 'pool', 'transit'], tags: ['View sông', 'Kết nối nhanh'] },
  { id: 'greenloop', name: 'Green Loop Thủ Đức', developer: 'Mẫu dữ liệu · New city', area: 'thu-duc', price: 3.7, unit: '2PN · 65–72 m²', rooms: [1, 2], amenities: ['park', 'parking', 'quiet'], tags: ['Giá dễ tiếp cận', 'Yên tĩnh'] },
  { id: 'lotus', name: 'Lotus Garden Tân Phú', developer: 'Mẫu dữ liệu · West side', area: 'tan-phu', price: 3.9, unit: '2PN · 68–75 m²', rooms: [1, 2, 3], amenities: ['school', 'park', 'parking', 'quiet'], tags: ['Gia đình trẻ', 'Nhiều mảng xanh'] },
  { id: 'novah', name: 'Nova Heights Gò Vấp', developer: 'Mẫu dữ liệu · North west', area: 'go-vap', price: 3.4, unit: '2PN · 62–70 m²', rooms: [1, 2], amenities: ['school', 'parking', 'quiet'], tags: ['Ngân sách tốt', 'Gần trường'] },
  { id: 'airport', name: 'Airport Link Tân Bình', developer: 'Mẫu dữ liệu · Airport belt', area: 'tan-binh', price: 5.2, unit: '2PN · 66–78 m²', rooms: [1, 2, 3], amenities: ['school', 'parking', 'transit'], tags: ['Gần sân bay', 'Đi lại tiện'] },
  { id: 'harbor', name: 'Harbor Point Nhà Bè', developer: 'Mẫu dữ liệu · South gateway', area: 'nha-be', price: 4.6, unit: '2PN · 70–80 m²', rooms: [2, 3], amenities: ['park', 'parking', 'pool', 'quiet'], tags: ['Mật độ thấp', 'Nghỉ ngơi'] },
  { id: 'centralgate', name: 'Central Gate Quận 1', developer: 'Mẫu dữ liệu · Downtown', area: 'quan-1', price: 8.8, unit: '2PN · 62–74 m²', rooms: [1, 2, 3], amenities: ['parking', 'transit'], tags: ['Ngay lõi trung tâm', 'Khan hiếm'] },
  { id: 'saigonrise', name: 'Saigon Rise Quận 7', developer: 'Mẫu dữ liệu · South side', area: 'quan-7', price: 6.8, unit: '3PN · 86–102 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool', 'quiet'], tags: ['3 phòng ngủ', 'Tiện ích đầy đủ'] },
  { id: 'parkview', name: 'Parkview Bình Chánh', developer: 'Mẫu dữ liệu · South west', area: 'binh-chanh', price: 3.1, unit: '2PN · 63–70 m²', rooms: [1, 2], amenities: ['park', 'parking', 'quiet'], tags: ['Giá mềm', 'Nhiều cây xanh'] },
  { id: 'thegrove', name: 'The Grove Bình Thạnh', developer: 'Mẫu dữ liệu · Inner city', area: 'binh-thanh', price: 6.9, unit: '3PN · 88–98 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool'], tags: ['Gia đình lớn', 'Kề trung tâm'] },
  { id: 'skyline', name: 'Skyline An Phú', developer: 'Mẫu dữ liệu · Thu Duc core', area: 'thu-duc', price: 7.2, unit: '2PN · 74–88 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool', 'transit'], tags: ['Tiện ích cao cấp', 'Khu đô thị'] },
  { id: 'orchid', name: 'Orchid Residence Tân Phú', developer: 'Mẫu dữ liệu · West side', area: 'tan-phu', price: 4.8, unit: '3PN · 80–92 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool', 'quiet'], tags: ['Rộng rãi', 'Yên tĩnh'] },
  { id: 'elevate', name: 'Elevate Gò Vấp', developer: 'Mẫu dữ liệu · North west', area: 'go-vap', price: 4.1, unit: '2PN · 65–73 m²', rooms: [1, 2], amenities: ['school', 'parking', 'quiet', 'transit'], tags: ['Dễ mua', 'Gần tiện ích'] },
  { id: 'sunbay', name: 'Sunbay Phú Mỹ Hưng', developer: 'Mẫu dữ liệu · South side', area: 'quan-7', price: 7.9, unit: '3PN · 92–110 m²', rooms: [2, 3], amenities: ['school', 'park', 'parking', 'pool', 'quiet'], tags: ['Cộng đồng tốt', '3 phòng ngủ'] },
  { id: 'urbania', name: 'Urbania Tân Bình', developer: 'Mẫu dữ liệu · Airport belt', area: 'tan-binh', price: 6.4, unit: '2PN · 70–80 m²', rooms: [1, 2, 3], amenities: ['school', 'parking', 'transit'], tags: ['Cận trung tâm', 'Thanh khoản tốt'] }
];

const form = document.querySelector('#matching-form');
const recommendations = document.querySelector('#recommendations');
const favoriteProject = document.querySelector('#favorite-project');
const comparisonContent = document.querySelector('#comparison-content');
const insightText = document.querySelector('#insight-text');
const resultsTitle = document.querySelector('#results-title');
const lastRun = document.querySelector('#last-run');
const toast = document.querySelector('#toast');
let latestResults = [];
let latestProfile = null;
let toastTimer;

const formatPrice = (value) => value.toFixed(1).replace('.', ',') + ' tỷ';
const formatMoney = (value) => value.toFixed(1).replace('.', ',') + ' triệu/tháng';
const clamp = (value, min = 0, max = 100) => Math.min(max, Math.max(min, value));

function haversineDistance(from, to) {
  if (!from || !to) return 0;
  const radians = (value) => value * Math.PI / 180;
  const earthRadius = 6371;
  const latitudeDelta = radians(to[0] - from[0]);
  const longitudeDelta = radians(to[1] - from[1]);
  const a = Math.sin(latitudeDelta / 2) ** 2 + Math.cos(radians(from[0])) * Math.cos(radians(to[0])) * Math.sin(longitudeDelta / 2) ** 2;
  return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function monthlyPayment(principalBillion) {
  if (principalBillion <= 0) return 0;
  const monthlyRate = 0.085 / 12;
  const months = 240;
  const principal = principalBillion * 1000;
  return principal * monthlyRate * ((1 + monthlyRate) ** months) / (((1 + monthlyRate) ** months) - 1);
}

function collectProfile() {
  return {
    name: document.querySelector('#client-name').value.trim() || 'khách hàng',
    workplace: document.querySelector('#workplace').value,
    school: document.querySelector('#school').value,
    budget: Number(document.querySelector('#budget').value) || 0,
    downPayment: Number(document.querySelector('#down-payment').value) || 0,
    income: Number(document.querySelector('#income').value) || 0,
    bedrooms: Number(document.querySelector('#bedrooms').value),
    amenities: [...document.querySelectorAll('input[name="amenity"]:checked')].map((input) => input.value),
    favoriteId: favoriteProject.value
  };
}

function scoreProject(project, profile) {
  const workDistance = haversineDistance(areaCoordinates[profile.workplace], areaCoordinates[project.area]);
  const schoolDistance = profile.school === 'none' ? 0 : haversineDistance(areaCoordinates[profile.school], areaCoordinates[project.area]);
  const blendedDistance = profile.school === 'none' ? workDistance : workDistance * .7 + schoolDistance * .3;
  const commuteScore = clamp(100 * Math.exp(-blendedDistance / 13));
  const monthly = monthlyPayment(Math.max(project.price - Math.min(profile.downPayment, profile.budget), 0));
  const paymentRatio = profile.income > 0 ? monthly / profile.income : 1;
  const priceOverBudget = Math.max(project.price - profile.budget, 0);
  const financeScore = clamp(100 - Math.max(paymentRatio - .25, 0) * 190 - priceOverBudget * 9);
  const amenityScore = profile.amenities.length === 0 ? 68 : clamp(30 + project.amenities.filter((item) => profile.amenities.includes(item)).length / profile.amenities.length * 70);
  const roomScore = project.rooms.includes(profile.bedrooms) ? 100 : 48;
  const score = Math.round(commuteScore * .4 + financeScore * .35 + amenityScore * .2 + roomScore * .05);
  return Object.assign({}, project, { score, workDistance, schoolDistance, blendedDistance, commuteScore, financeScore, amenityScore, roomScore, monthly, paymentRatio });
}

function scoreLabel(score) {
  return score >= 80 ? 'Rất phù hợp' : score >= 65 ? 'Đáng cân nhắc' : 'Cần cân đối';
}

function getReason(project, profile) {
  const reasons = [];
  if (project.commuteScore >= 78) reasons.push('gần nơi làm việc');
  else if (project.financeScore >= 74) reasons.push('dòng tiền nhẹ');
  else if (project.amenityScore >= 78) reasons.push('đủ tiện ích');
  else reasons.push('có phương án thay thế');
  if (profile.amenities.some((item) => project.amenities.includes(item))) reasons.push('đúng ưu tiên sống');
  return reasons.slice(0, 2).join(' · ');
}

function projectCard(project, index) {
  const tags = project.tags.map((tag) => '<span>' + tag + '</span>').join('');
  return '<article class="recommendation-card' + (index === 0 ? ' top-choice' : '') + '">' +
    '<div class="project-main"><div class="rank-label">' + (index === 0 ? '✦  GỢI Ý SỐ 01' : '0' + (index + 1) + '  ·  GỢI Ý PHÙ HỢP') + '</div><h4>' + project.name + '</h4><div class="project-meta">' + project.developer + ' · ' + project.unit + '</div><div class="project-tags">' + tags + '</div><div class="fit-reason">' + getReason(project, latestProfile) + '</div></div>' +
+    '<div class="project-detail"><div class="detail-line"><small>Giá tham chiếu</small><strong>' + formatPrice(project.price) + '</strong></div><div class="detail-line"><small>Trả góp ước tính</small><strong class="money">' + formatMoney(project.monthly) + '</strong></div><div class="detail-line"><small>Đến nơi làm việc</small><strong>' + project.workDistance.toFixed(1).replace('.', ',') + ' km</strong></div></div>' +
+    '<div class="score-box"><div class="score-ring" style="--score:' + project.score + '%"><span class="score-number">' + project.score + '</span></div><span class="score-caption">' + scoreLabel(project.score) + '</span></div></article>';
}

function renderComparison(favorite, recommended) {
  if (!favorite || !recommended) {
    comparisonContent.innerHTML = '<div class="empty-state"><div class="empty-icon">⇄</div><strong>Chọn một dự án khách đang thích</strong><p>MinFit sẽ chỉ ra điểm mạnh và điểm cần cân đối so với gợi ý số 01.</p></div>';
    return;
  }
  const distanceDelta = favorite.blendedDistance - recommended.blendedDistance;
  const monthlyDelta = favorite.monthly - recommended.monthly;
  const distanceText = Math.abs(distanceDelta) < .4 ? 'Khoảng cách tương đương' : distanceDelta > 0 ? 'Xa hơn ' + distanceDelta.toFixed(1).replace('.', ',') + ' km' : 'Gần hơn ' + Math.abs(distanceDelta).toFixed(1).replace('.', ',') + ' km';
  const financeText = Math.abs(monthlyDelta) < 1 ? 'Áp lực tài chính tương đương' : monthlyDelta > 0 ? 'Cao hơn ' + formatMoney(monthlyDelta) : 'Nhẹ hơn ' + formatMoney(Math.abs(monthlyDelta));
  const amenityText = favorite.amenityScore >= recommended.amenityScore ? 'Tiện ích đang nhỉnh hơn' : 'Gợi ý mới khớp tiện ích hơn';
  comparisonContent.innerHTML = '<div class="compare-grid"><div class="compare-project"><small>Dự án khách thích</small><h4>' + favorite.name + '</h4><p>' + favorite.unit + ' · ' + formatPrice(favorite.price) + '</p><div class="mini-score">' + favorite.score + '<span>/ 100</span></div></div><div class="compare-arrow">→</div><div class="compare-project recommended"><small>Gợi ý số 01</small><h4>' + recommended.name + '</h4><p>' + recommended.unit + ' · ' + formatPrice(recommended.price) + '</p><div class="mini-score">' + recommended.score + '<span>/ 100</span></div></div></div><div class="compare-insights"><div class="compare-insight ' + (distanceDelta > .4 ? 'positive' : distanceDelta < -.4 ? 'warning' : 'neutral') + '"><b>Đi lại</b>' + distanceText + ' so với phương án đang thích.</div><div class="compare-insight ' + (monthlyDelta > 1 ? 'positive' : monthlyDelta < -1 ? 'warning' : 'neutral') + '"><b>Tài chính</b>' + financeText + ' theo khoản vay 20 năm.</div><div class="compare-insight ' + (favorite.amenityScore >= recommended.amenityScore ? 'warning' : 'positive') + '"><b>Sinh hoạt</b>' + amenityText + ' theo tiêu chí đã chọn.</div></div>';
}

function updateInsight(results, profile) {
  const first = results[0];
  if (!first) { insightText.textContent = 'Chưa có dự án trong kho dữ liệu phù hợp với bộ lọc hiện tại.'; return; }
  const clientName = profile.name === 'khách hàng' ? 'Hồ sơ hiện tại' : profile.name;
  const reason = first.commuteScore >= first.financeScore && first.commuteScore >= first.amenityScore ? 'gần khu vực làm việc' : first.financeScore >= first.amenityScore ? 'giữ áp lực trả góp ở mức dễ thở hơn' : 'khớp tốt các tiện ích gia đình cần';
  insightText.textContent = clientName + ': ' + first.name + ' đang dẫn đầu với ' + first.score + '/100 nhờ ' + reason + '. Đây là điểm bắt đầu tốt cho cuộc tư vấn, không thay thế thẩm định tài chính thực tế.';
}

function runMatching(event) {
  if (event) event.preventDefault();
  if (!form.reportValidity()) return;
  const profile = collectProfile();
  latestProfile = profile;
  const scored = projects.map((project) => scoreProject(project, profile));
  latestResults = scored.sort((a, b) => b.score - a.score).slice(0, 3);
  resultsTitle.textContent = '3 dự án phù hợp nhất cho ' + profile.name;
  recommendations.innerHTML = latestResults.map(projectCard).join('');
  updateInsight(latestResults, profile);
  renderComparison(scored.find((project) => project.id === profile.favoriteId), latestResults[0]);
  lastRun.textContent = 'Cập nhật lúc ' + new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

function summaryText() {
  if (!latestProfile || !latestResults.length) return 'Chưa có kết quả. Hãy chạy phân tích trên MinFit AI trước.';
  const lines = ['MINFIT AI · TÓM TẮT GỢI Ý', 'Khách hàng: ' + latestProfile.name, 'Nhu cầu: làm việc tại ' + latestProfile.workplace + ', ngân sách ' + formatPrice(latestProfile.budget) + ', vốn sẵn có ' + formatPrice(latestProfile.downPayment) + ', thu nhập ' + latestProfile.income + ' triệu/tháng', '', 'TOP 3 DỰ ÁN PHÙ HỢP'];
  latestResults.forEach((project, index) => lines.push((index + 1) + '. ' + project.name + ' · Fit Score ' + project.score + '/100 · ' + formatPrice(project.price) + ' · ' + project.unit + ' · Trả góp khoảng ' + formatMoney(project.monthly)));
  lines.push('', 'Lưu ý: Đây là ước tính từ dữ liệu demo, cần kiểm tra lại bảng giá, lãi suất và lịch di chuyển thực tế trước khi tư vấn.');
  return lines.join('\n');
}

function showToast(message) { window.clearTimeout(toastTimer); toast.textContent = message; toast.classList.add('show'); toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2400); }
function populateFavoriteProjects() { favoriteProject.innerHTML = '<option value="">Chưa chọn dự án</option>' + projects.map((project) => '<option value="' + project.id + '">' + project.name + '</option>').join(''); favoriteProject.value = 'centralgate'; }

document.querySelector('#copy-summary').addEventListener('click', async () => { try { await navigator.clipboard.writeText(summaryText()); showToast('Đã sao chép tóm tắt vào clipboard'); } catch { showToast('Trình duyệt không cho phép sao chép tự động'); } });
document.querySelector('#download-summary').addEventListener('click', () => { const blob = new Blob([summaryText()], { type: 'text/plain;charset=utf-8' }); const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'minfit-tom-tat-tu-van.txt'; link.click(); URL.revokeObjectURL(link.href); showToast('Đã tải file tóm tắt tư vấn'); });
document.querySelector('#reset-form').addEventListener('click', () => { form.reset(); document.querySelector('#workplace').value = 'binh-thanh'; document.querySelector('#school').value = 'none'; document.querySelector('#budget').value = '6.5'; document.querySelector('#down-payment').value = '1.8'; document.querySelector('#income').value = '80'; document.querySelector('#bedrooms').value = '2'; favoriteProject.value = 'centralgate'; recommendations.innerHTML = '<div class="empty-state"><div class="empty-icon">✦</div><strong>Sẵn sàng tìm phương án phù hợp</strong><p>Điền hồ sơ khách hàng và bắt đầu phiên phân tích mới.</p></div>'; resultsTitle.textContent = '3 dự án phù hợp nhất'; insightText.textContent = 'Thiết lập hồ sơ bên trái để MinFit bắt đầu tìm phương án phù hợp.'; comparisonContent.innerHTML = '<div class="empty-state"><div class="empty-icon">⇄</div><strong>Chọn một dự án khách đang thích</strong><p>MinFit sẽ chỉ ra điểm mạnh và điểm cần cân đối so với gợi ý số 01.</p></div>'; latestResults = []; latestProfile = null; lastRun.textContent = 'Vừa cập nhật'; showToast('Đã làm mới hồ sơ'); });
form.addEventListener('submit', runMatching);
populateFavoriteProjects();
runMatching();
